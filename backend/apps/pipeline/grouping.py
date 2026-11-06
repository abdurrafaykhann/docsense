"""Turn OCR words into reading-order text lines for the prompt (M7 adds per-region grouping)."""

from __future__ import annotations

from statistics import median

from apps.validation.grounding import Word

from .layout import Region


def words_to_lines(words: list[Word]) -> list[list[Word]]:
    if not words:
        return []
    h = median(w.y1 - w.y0 for w in words) or 0.01
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        yc = (w.y0 + w.y1) / 2
        placed = False
        if lines:
            last = lines[-1]
            ref = sum((x.y0 + x.y1) / 2 for x in last) / len(last)
            if abs(yc - ref) <= 0.6 * h:
                last.append(w)
                placed = True
        if not placed:
            lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def lines_to_text(lines: list[list[Word]]) -> str:
    out = []
    for line in lines:
        h = median(w.y1 - w.y0 for w in line) or 0.01
        parts = [line[0].text]
        for prev, cur in zip(line, line[1:], strict=False):
            parts.append(" | " if cur.x0 - prev.x1 > 3 * h else " ")
            parts.append(cur.text)
        out.append("".join(parts))
    return "\n".join(out)


def pages_to_prompt_text(words_by_page: dict[int, list[Word]], max_chars: int) -> str:
    chunks = []
    for page, words in sorted(words_by_page.items()):
        chunks.append(f"--- page {page} ---\n{lines_to_text(words_to_lines(words))}")
    return "\n".join(chunks)[:max_chars]


SECTION_ORDER = ["vendor", "meta", "table", "totals", "other"]
OTHER_MAX_CHARS = 400  # footers/terms rarely hold fields: keep them short to save tokens


def _overlap_fraction(w: Word, r: Region) -> float:
    ix = max(0.0, min(w.x1, r.bbox[2]) - max(w.x0, r.bbox[0]))
    iy = max(0.0, min(w.y1, r.bbox[3]) - max(w.y0, r.bbox[1]))
    area = max((w.x1 - w.x0) * (w.y1 - w.y0), 1e-9)
    return ix * iy / area


def assign_words(words: list[Word], regions: list[Region]) -> dict[str, list[Word]]:
    """Each word goes to the most specific (smallest) region covering >=50% of it, else 'other'."""
    out: dict[str, list[Word]] = {c: [] for c in SECTION_ORDER}
    for w in words:
        hits = [r for r in regions if _overlap_fraction(w, r) >= 0.5]
        cls = min(hits, key=lambda r: r.area).cls if hits else "other"
        out[cls if cls in out else "other"].append(w)
    return out


def regions_usable(regions: list[Region]) -> bool:
    """Layout is trusted only if it found the table or the totals block."""
    return any(r.cls in ("table", "totals") for r in regions)


def region_page_text(words: list[Word], regions: list[Region]) -> str:
    groups = assign_words(words, regions)
    parts = []
    for cls in SECTION_ORDER:
        if not groups[cls]:
            continue
        text = lines_to_text(words_to_lines(groups[cls]))
        if cls == "other":
            text = text[:OTHER_MAX_CHARS]
        parts.append(f"[{cls.upper()}]\n{text}")
    return "\n".join(parts)


def pages_to_region_prompt_text(
    words_by_page: dict[int, list[Word]], regions_by_page: dict[int, list[Region]], max_chars: int
) -> str:
    """Per-region prompt text; pages without a usable layout fall back to whole-page text."""
    chunks = []
    for page, words in sorted(words_by_page.items()):
        regions = regions_by_page.get(page, [])
        body = (
            region_page_text(words, regions)
            if regions_usable(regions)
            else lines_to_text(words_to_lines(words))
        )
        chunks.append(f"--- page {page} ---\n{body}")
    return "\n".join(chunks)[:max_chars]
