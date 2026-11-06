"""Turn OCR words into reading-order text lines for the prompt (M7 adds per-region grouping)."""

from __future__ import annotations

from statistics import median

from apps.validation.grounding import Word


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
