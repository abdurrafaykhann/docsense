"""Locate an extracted value in the OCR words (gives a bbox + OCR confidence + grounding score)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from rapidfuzz import fuzz

from .schema import NUMERIC_FIELDS, to_number


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 1.0
    page: int = 1

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "bbox": [self.x0, self.y0, self.x1, self.y1],
            "conf": self.conf,
            "page": self.page,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Word:
        x0, y0, x1, y1 = d["bbox"]
        return cls(d["text"], x0, y0, x1, y1, d.get("conf", 1.0), d.get("page", 1))


@dataclass
class Location:
    page: int
    bbox: list[float]  # normalised [x0, y0, x1, y1]
    conf: float  # mean OCR confidence of the matched words
    match: float  # 0..1 how well the text matched

    def as_dict(self) -> dict:
        return {"page": self.page, "bbox": self.bbox, "conf": self.conf, "match": self.match}


MATCH_OK = 0.85
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _union(words: list[Word]) -> list[float]:
    return [
        min(w.x0 for w in words),
        min(w.y0 for w in words),
        max(w.x1 for w in words),
        max(w.y1 for w in words),
    ]


def _loc(words: list[Word], match: float) -> Location:
    return Location(words[0].page, _union(words), sum(w.conf for w in words) / len(words), match)


def _norm(s: str) -> str:
    return re.sub(r"[^\w]", "", s.lower())


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _windows(words: list[Word], max_len: int):
    for i in range(len(words)):
        for n in range(1, max_len + 1):
            if i + n <= len(words):
                yield words[i : i + n]


def date_variants(iso: str) -> list[str]:
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
    except ValueError:
        return [iso]
    mon = _MONTHS[d.month - 1]
    return [
        iso,
        d.strftime("%d/%m/%Y"),
        d.strftime("%d-%m-%Y"),
        d.strftime("%d.%m.%Y"),
        d.strftime("%d/%m/%y"),
        f"{d.day}/{d.month}/{d.year}",
        f"{d.day}-{mon}-{d.year}",
        f"{d.day:02d}-{mon}-{d.year}",
        f"{d.day} {mon} {d.year}",
        f"{d.day:02d} {mon} {d.year}",
        f"{mon} {d.day}, {d.year}",
    ]


def locate(name: str, value, words: list[Word]) -> Location | None:
    """Best location of `value` among `words` (reading order), or None if not found."""
    if value in (None, "") or not words:
        return None

    if name in NUMERIC_FIELDS:
        target = float(value)
        hits = []
        for w in words:
            n = to_number(w.text)
            if n is not None and abs(n - target) < 0.005 and re.search(r"\d", w.text):
                hits.append(w)
        if not hits:
            return None
        return _loc([hits[-1]], 1.0)  # totals sit at the bottom: take the last occurrence

    if name == "invoice_date":
        variants = [_norm(v) for v in date_variants(str(value))]
        best: tuple[float, list[Word]] | None = None
        for win in _windows(words, 4):
            text = _norm("".join(w.text for w in win))
            score = max(fuzz.ratio(text, v) / 100 for v in variants)
            if best is None or score > best[0]:
                best = (score, win)
        return _loc(best[1], best[0]) if best and best[0] >= MATCH_OK else None

    if name in ("ntn", "strn"):
        target = _digits(str(value))
        if not target:
            return None
        for win in _windows(words, 3):
            if _digits("".join(w.text for w in win)) == target:
                return _loc(win, 1.0)
        return None

    if name == "currency":
        return None

    target = _norm(str(value))
    if not target:
        return None
    max_len = len(str(value).split()) + 1
    best = None
    for win in _windows(words, max_len):
        score = fuzz.ratio(_norm("".join(w.text for w in win)), target) / 100
        if best is None or score > best[0]:
            best = (score, win)
    return _loc(best[1], best[0]) if best and best[0] >= MATCH_OK else None


def words_from_lines(lines: list[str], page: int = 1, conf: float = 0.98) -> list[Word]:
    """Lay out text lines top-to-bottom as words (used by the fake OCR and by tests)."""
    words: list[Word] = []
    n = len(lines)
    for i, line in enumerate(lines):
        toks = line.split()
        y0 = (i + 0.5) / (n + 1)
        x = 0.05
        for tok in toks:
            w = min(0.9, 0.012 * len(tok) + 0.01)
            words.append(Word(tok, x, y0, x + w, y0 + 0.5 / (n + 1), conf, page))
            x += w + 0.01
    return words
