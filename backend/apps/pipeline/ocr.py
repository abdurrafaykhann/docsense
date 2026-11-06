"""OCR engines behind one interface. docTR (PyTorch) in production, FakeOCR in tests."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from apps.validation.grounding import Word, words_from_lines


class OCREngine(Protocol):
    def read(self, image: np.ndarray, page: int = 1) -> list[Word]: ...


class FakeOCR:
    """Returns scripted text lines laid out top-to-bottom (ignores the image)."""

    def __init__(self, lines: list[str] | None = None, conf: float = 0.98):
        self.lines, self.conf = lines or [], conf
        self.calls = 0

    def read(self, image: np.ndarray, page: int = 1) -> list[Word]:
        self.calls += 1
        return words_from_lines(self.lines, page=page, conf=self.conf)


class DocTROCR:
    """docTR: DB (MobileNetV3) text detection + CRNN recognition. Lazy-loaded, CPU-friendly."""

    _predictor = None

    @classmethod
    def predictor(cls):
        if cls._predictor is None:
            from doctr.models import ocr_predictor

            cls._predictor = ocr_predictor(
                det_arch="db_mobilenet_v3_large",
                reco_arch="crnn_mobilenet_v3_small",
                pretrained=True,
            )
        return cls._predictor

    def read(self, image: np.ndarray, page: int = 1) -> list[Word]:
        result = self.predictor()([image])
        words: list[Word] = []
        for blk in result.pages[0].blocks:
            for line in blk.lines:
                for w in line.words:
                    (x0, y0), (x1, y1) = w.geometry
                    words.append(Word(w.value, x0, y0, x1, y1, float(w.confidence), page))
        # reading order: top-to-bottom bands, then left-to-right
        words.sort(key=lambda w: (round((w.y0 + w.y1) / 2 / 0.012), w.x0))
        return words
