"""Layout class names (YOLO class ids 0..4) and the dataset file helper.

No dependencies on purpose: the retrain step runs inside the app image and must be able to import
this without the synthetic-data libraries (faker, jinja2, playwright, albumentations) that
``synth.render`` and ``synth.build`` need.
"""

from pathlib import Path

CLASSES = ["vendor", "meta", "table", "totals", "other"]


def write_data_yaml(root: Path, train: str = "images/train", val: str = "images/val") -> None:
    """Ultralytics dataset file for a YOLO dataset folder (used by training and retraining)."""
    (root / "data.yaml").write_text(
        f"path: {root.resolve().as_posix()}\ntrain: {train}\nval: {val}\nnames:\n"
        + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)),
        encoding="utf-8",
    )
