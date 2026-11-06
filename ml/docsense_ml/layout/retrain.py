"""Fine-tune the current layout model on human-approved feedback and compare old vs new.

Invoked by the backend (`manage.py retrain_layout` / admin button):

    python -m docsense_ml.layout.retrain --feedback F --base current.pt --out DIR --epochs 5

Prints one line `RESULT {json}` with mAP@50 of the previous and the new weights on every
evaluation set available, so the caller can decide whether to activate the new model.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from ..synth.render import CLASSES
from . import yolo

FEEDBACK_COPIES = 3  # human-confirmed samples are scarce: oversample them next to synthetic data
HOLDOUT_EVERY = 5  # every 5th feedback sample is held out to measure learning on real usage
MIN_HOLDOUT = 10
# Gentle fine-tuning: an explicit optimizer (Ultralytics' "auto" ignores lr0 and picks a hot rate
# for short runs, which wrecked the model in the first end-to-end test) and a small learning rate.
FINE_TUNE = {"optimizer": "AdamW", "lr0": 0.0003, "lrf": 0.1, "warmup_epochs": 0.0}


def _yaml(path: Path, root: Path, train, val) -> Path:
    trains = train if isinstance(train, list) else [train]
    path.write_text(
        f"path: {root.resolve().as_posix()}\n"
        + "train:\n"
        + "".join(f"  - {Path(t).resolve().as_posix()}\n" for t in trains)
        + f"val: {Path(val).resolve().as_posix()}\n"
        + "names:\n"
        + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)),
        encoding="utf-8",
    )
    return path


def split_feedback(feedback: Path, work: Path) -> tuple[Path, Path | None]:
    """Return (train_images_dir, holdout_images_dir|None); copies are made under `work`."""
    images = sorted((feedback / "images" / "train").glob("*.jpg"))
    labels = feedback / "labels" / "train"
    hold = len(images) >= MIN_HOLDOUT * 1  # need enough samples for a meaningful holdout
    train_dir, hold_dir = work / "fb" / "images" / "train", work / "fb_hold" / "images" / "val"
    for d in (train_dir, work / "fb" / "labels" / "train"):
        d.mkdir(parents=True, exist_ok=True)
    if hold:
        hold_dir.mkdir(parents=True, exist_ok=True)
        (work / "fb_hold" / "labels" / "val").mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(images):
        lab = labels / f"{img.stem}.txt"
        if hold and i % HOLDOUT_EVERY == HOLDOUT_EVERY - 1:
            shutil.copy(img, hold_dir / img.name)
            shutil.copy(lab, work / "fb_hold" / "labels" / "val" / lab.name)
        else:
            for k in range(FEEDBACK_COPIES):
                shutil.copy(img, train_dir / f"{img.stem}_{k}.jpg")
                shutil.copy(lab, work / "fb" / "labels" / "train" / f"{img.stem}_{k}.txt")
    return train_dir, (hold_dir if hold else None)


def run(feedback: Path, base: Path, out: Path, synth: Path, real: Path, epochs: int, imgsz: int):
    out = Path(out)
    work = out / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    fb_train, fb_hold = split_feedback(Path(feedback), work)
    synth_full = Path(synth) / "full"
    # Replay: a model fine-tuned only on new feedback forgets what it learned from its original
    # ingredients (the first end-to-end retrain dropped real mAP from 0.71 to 0.02). Keep every
    # ingredient the base model was trained on that exists on this machine.
    # Same synthetic ingredient as the base model (scene placement when available, otherwise full
    # augmentation): mixing in a second, full-frame synthetic set diluted the real receipts and
    # pulled the model back toward full-frame pages (second end-to-end retrain: real 0.71 -> 0.45).
    scene = Path(synth) / "scene" / "images" / "train"
    train_dirs = [scene if scene.exists() else synth_full / "images" / "train", fb_train]
    if (Path(real) / "images" / "tune").exists():
        from .experiments import pseudo_label_mix

        mix = work / "real_replay"
        pseudo_label_mix(base, Path(real), mix, imgsz)
        train_dirs.append(mix / "images" / "train")
    train_yaml = _yaml(work / "train.yaml", work, train_dirs, synth_full / "images" / "val")

    eval_sets: dict[str, Path] = {}
    if (Path(synth) / "valfull" / "data.yaml").exists():
        eval_sets["synthetic-hard"] = Path(synth) / "valfull" / "data.yaml"
    if (Path(real) / "data.yaml").exists():
        eval_sets["cord-real-test"] = Path(real) / "data.yaml"
    if fb_hold is not None:
        eval_sets["feedback-holdout"] = _yaml(work / "holdout.yaml", work, fb_hold, fb_hold)

    previous = {n: yolo.evaluate(base, y, imgsz=imgsz) for n, y in eval_sets.items()}
    best = yolo.train(
        train_yaml,
        "retrain",
        epochs=epochs,
        imgsz=imgsz,
        base=str(base),
        project=out / "yolo",
        overrides=FINE_TUNE,
    )
    new = {n: yolo.evaluate(best, y, imgsz=imgsz) for n, y in eval_sets.items()}

    final = out / f"layout-{datetime.now():%Y%m%d-%H%M%S}.pt"
    shutil.copy(best, final)
    return {"previous": previous, "new": new, "weights": str(final.resolve())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feedback", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--synth", default="ml/data/synth")
    ap.add_argument("--real", default="ml/data/cord_layout")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--imgsz", type=int, default=416)
    a = ap.parse_args()
    result = run(
        Path(a.feedback), Path(a.base), Path(a.out), Path(a.synth), Path(a.real), a.epochs, a.imgsz
    )
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()
