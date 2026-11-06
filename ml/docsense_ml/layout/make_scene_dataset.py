"""Build the 'scene' dataset from the clean synthetic renders (no browser needed).

python -m docsense_ml.layout.make_scene_dataset --synth ml/data/synth
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from ..synth.augment import augment
from ..synth.build import _save, _write_labels, write_data_yaml
from ..synth.scene import place_on_scene


def read_labels(path: Path):
    boxes, labels = [], []
    for line in path.read_text().splitlines():
        c, cx, cy, w, h = line.split()
        labels.append(int(c))
        boxes.append([float(cx), float(cy), float(w), float(h)])
    return boxes, labels


def build(synth: Path, variants: int = 1, seed: int = 0) -> dict:
    src, out = synth / "none", synth / "scene"
    counts = {"train": 0}
    for img_path in sorted((src / "images" / "train").glob("*.jpg")):
        boxes, labels = read_labels(src / "labels" / "train" / f"{img_path.stem}.txt")
        img = np.array(Image.open(img_path).convert("RGB"))
        for k in range(variants):
            rng = np.random.default_rng([seed, int(img_path.stem[1:]), k])
            scene, bx = place_on_scene(img, boxes, rng)
            scene, bx, lb = augment(scene, bx, labels, "full", seed=int(rng.integers(0, 2**31)))
            name = f"{img_path.stem}_{k}"
            _save(scene, out / "images" / "train" / f"{name}.jpg")
            _write_labels(out / "labels" / "train" / f"{name}.txt", bx, lb)
            counts["train"] += 1
    # validation: the same hard-synthetic set used by every other experiment
    write_data_yaml(
        out, train="images/train", val=str((synth / "valfull" / "images" / "val").resolve())
    )
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synth", default="ml/data/synth")
    ap.add_argument("--variants", type=int, default=1)
    a = ap.parse_args()
    print(build(Path(a.synth), a.variants))


if __name__ == "__main__":
    main()
