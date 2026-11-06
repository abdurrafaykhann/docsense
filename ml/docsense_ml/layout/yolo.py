"""Train / evaluate the layout detector (Ultralytics YOLO, AGPL-3.0) on CPU or GPU.

Built-in Ultralytics augmentation is switched OFF so that the only photometric/geometric
difference between experiments is OUR Albumentations pipeline (ablation stays clean). Horizontal
flip is never used: it mirrors text and would teach the model unreal layouts.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..synth.render import CLASSES

NO_BUILTIN_AUG = {
    "mosaic": 0.0,
    "mixup": 0.0,
    "hsv_h": 0.0,
    "hsv_s": 0.0,
    "hsv_v": 0.0,
    "degrees": 0.0,
    "translate": 0.0,
    "scale": 0.0,
    "shear": 0.0,
    "perspective": 0.0,
    "flipud": 0.0,
    "fliplr": 0.0,
    "erasing": 0.0,
    "close_mosaic": 0,
}


def train(
    data_yaml: str | Path,
    name: str,
    *,
    epochs: int = 12,
    imgsz: int = 480,
    batch: int = 16,
    base: str = "yolo11n.pt",
    project: str | Path = "ml/runs/yolo",
    device: str = "cpu",
    seed: int = 0,
    workers: int = 4,
    overrides: dict | None = None,
) -> Path:
    from ultralytics import YOLO

    model = YOLO(base)
    model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        workers=workers,
        project=str(Path(project).resolve()),
        name=name,
        exist_ok=True,
        seed=seed,
        deterministic=True,
        patience=epochs,
        plots=True,
        amp=False,
        verbose=False,
        **{**NO_BUILTIN_AUG, **(overrides or {})},
    )
    return Path(project).resolve() / name / "weights" / "best.pt"


def read_results(run_dir: str | Path) -> list[dict]:
    """Per-epoch metrics from Ultralytics' results.csv (for MLflow)."""
    path = Path(run_dir) / "results.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [{k.strip(): float(v) for k, v in r.items() if v.strip()} for r in rows]


def evaluate(
    weights: str | Path,
    data_yaml: str | Path,
    *,
    imgsz: int = 480,
    split: str = "val",
    device: str = "cpu",
) -> dict:
    """mAP@50 per class. Classes with no ground truth in the set are reported as None."""
    from ultralytics import YOLO

    model = YOLO(str(weights))
    m = model.val(
        data=str(data_yaml),
        imgsz=imgsz,
        split=split,
        device=device,
        conf=0.001,
        iou=0.6,
        plots=False,
        verbose=False,
    )
    names = model.names
    present = {
        names[int(c)]: float(ap) for c, ap in zip(m.box.ap_class_index, m.box.ap50, strict=True)
    }
    return {
        "map50": round(float(m.box.map50), 4),
        "map50_95": round(float(m.box.map), 4),
        "per_class_ap50": {c: (round(present[c], 4) if c in present else None) for c in CLASSES},
    }
