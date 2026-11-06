"""Decode uploads (PDF or image) to RGB arrays, one per page."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageOps


def load_pages(
    data: bytes, content_type: str, max_pages: int = 6, dpi: int = 200
) -> list[np.ndarray]:
    if content_type == "application/pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        try:
            n = min(len(pdf), max_pages)
            return [
                np.array(pdf[i].render(scale=dpi / 72).to_pil().convert("RGB")) for i in range(n)
            ]
        finally:
            pdf.close()
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    return [np.array(img)]


def encode_jpeg(img: np.ndarray, quality: int = 88) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "JPEG", quality=quality)
    return buf.getvalue()
