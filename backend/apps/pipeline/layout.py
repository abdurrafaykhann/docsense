"""Layout detection: my fine-tuned YOLO finds vendor / meta / table / totals / other regions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

CLASSES = ["vendor", "meta", "table", "totals", "other"]
UNIQUE = {"vendor", "meta", "table", "totals"}  # a receipt has one of each; 'other' may repeat


@dataclass
class Region:
    cls: str
    bbox: list[float]  # normalised [x0, y0, x1, y1]
    score: float = 1.0
    page: int = 1

    def as_dict(self) -> dict:
        return {"cls": self.cls, "bbox": self.bbox, "score": self.score, "page": self.page}

    @property
    def area(self) -> float:
        return max(0.0, self.bbox[2] - self.bbox[0]) * max(0.0, self.bbox[3] - self.bbox[1])


class LayoutDetector(Protocol):
    def detect(self, image: np.ndarray, page: int = 1) -> list[Region]: ...


def keep_best_per_class(regions: list[Region]) -> list[Region]:
    """One box per unique class (highest score); every 'other' box kept."""
    best: dict[str, Region] = {}
    others: list[Region] = []
    for r in sorted(regions, key=lambda r: -r.score):
        if r.cls in UNIQUE:
            best.setdefault(r.cls, r)
        else:
            others.append(r)
    return sorted([*best.values(), *others], key=lambda r: r.bbox[1])


class FakeLayout:
    """Returns scripted regions (tests, oracle experiments)."""

    def __init__(self, regions: list[Region] | None = None):
        self.regions = regions or []
        self.calls = 0

    def detect(self, image: np.ndarray, page: int = 1) -> list[Region]:
        self.calls += 1
        return [Region(r.cls, r.bbox, r.score, page) for r in self.regions]


class YoloLayoutDetector:
    """Ultralytics YOLO weights trained in ml/ (CPU inference, ~0.1 s per page)."""

    def __init__(self, weights: str | Path, imgsz: int = 480, conf: float = 0.25):
        self.weights, self.imgsz, self.conf = str(weights), imgsz, conf
        self._model = None

    def _load(self):
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self.weights)
        return self._model

    def detect(self, image: np.ndarray, page: int = 1) -> list[Region]:
        model = self._load()
        res = model.predict(image, imgsz=self.imgsz, conf=self.conf, device="cpu", verbose=False)[0]
        h, w = image.shape[:2]
        out = []
        for cls, score, (x0, y0, x1, y1) in zip(
            res.boxes.cls.tolist(), res.boxes.conf.tolist(), res.boxes.xyxy.tolist(), strict=True
        ):
            out.append(
                Region(
                    model.names[int(cls)],
                    [round(x0 / w, 5), round(y0 / h, 5), round(x1 / w, 5), round(y1 / h, 5)],
                    round(float(score), 4),
                    page,
                )
            )
        return keep_best_per_class(out)
