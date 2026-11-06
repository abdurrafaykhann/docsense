"""Real docTR smoke test (downloads weights on first run). Run: pytest -m slow --force-enable-socket"""

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

pytestmark = [pytest.mark.slow, pytest.mark.enable_socket]

LINES = [
    "ACME TRADERS",
    "NTN 1234567-8",
    "Invoice No INV-0042",
    "Date 12/03/2024",
    "Total 3,540.00",
]


def font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def test_doctr_reads_printed_invoice_lines():
    pytest.importorskip("doctr")
    from apps.pipeline.ocr import DocTROCR

    img = Image.new("RGB", (900, 700), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(LINES):
        d.text((60, 60 + i * 110), line, fill="black", font=font(48))
    words = DocTROCR().read(np.array(img))
    text = " ".join(w.text for w in words).lower()
    for must in ("acme", "traders", "inv-0042", "3,540.00"):
        assert must in text, (must, text)
    assert all(0 <= w.x0 < w.x1 <= 1 and 0 <= w.y0 < w.y1 <= 1 for w in words)
