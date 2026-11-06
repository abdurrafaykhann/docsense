"""Chunking that keeps page numbers and bounding boxes."""

from __future__ import annotations

from dataclasses import dataclass

from apps.pipeline.grouping import words_to_lines
from apps.validation.grounding import Word

MAX_CHARS = 420
OVERLAP_LINES = 1


@dataclass
class ChunkData:
    page: int
    text: str
    bbox: list[float]  # union of the source words
    kind: str = "text"


def _union(words: list[Word]) -> list[float]:
    return [
        round(min(w.x0 for w in words), 5),
        round(min(w.y0 for w in words), 5),
        round(max(w.x1 for w in words), 5),
        round(max(w.y1 for w in words), 5),
    ]


def chunk_page(words: list[Word], page: int) -> list[ChunkData]:
    """Greedy line packing up to MAX_CHARS, one line of overlap, never crossing pages."""
    lines = words_to_lines(words)
    chunks: list[ChunkData] = []
    cur: list[list[Word]] = []
    size = 0
    for line in lines:
        text = " ".join(w.text for w in line)
        if cur and size + len(text) > MAX_CHARS:
            flat = [w for ln in cur for w in ln]
            chunks.append(
                ChunkData(page, "\n".join(" ".join(w.text for w in ln) for ln in cur), _union(flat))
            )
            cur = cur[-OVERLAP_LINES:] if OVERLAP_LINES else []
            size = sum(len(" ".join(w.text for w in ln)) for ln in cur)
        cur.append(line)
        size += len(text)
    if cur:
        flat = [w for ln in cur for w in ln]
        chunks.append(
            ChunkData(page, "\n".join(" ".join(w.text for w in ln) for ln in cur), _union(flat))
        )
    return chunks


def summary_text(name: str, data: dict) -> str:
    """Human-readable digest of the (human-corrected) extraction: answers 'who/when/how much'."""
    parts = [f"Document {name}."]
    if data.get("vendor_name"):
        parts.append(f"Vendor: {data['vendor_name']}.")
    if data.get("invoice_number"):
        parts.append(f"Invoice number: {data['invoice_number']}.")
    if data.get("invoice_date"):
        parts.append(f"Invoice date: {data['invoice_date']}.")
    cur = data.get("currency") or "PKR"
    for key, label in (("subtotal", "Subtotal"), ("sales_tax", "Sales tax"), ("total", "Total")):
        if data.get(key) is not None:
            parts.append(f"{label}: {cur} {data[key]:,.2f}.")
    if data.get("ntn"):
        parts.append(f"NTN: {data['ntn']}.")
    if data.get("strn"):
        parts.append(f"STRN: {data['strn']}.")
    items = [i for i in data.get("line_items", []) if i.get("description")]
    if items:
        parts.append(
            "Items: "
            + "; ".join(
                f"{i['description']} x{i.get('quantity') or 1} = {i.get('amount')}"
                for i in items[:12]
            )
            + "."
        )
    return " ".join(parts)
