"""Build a YOLO layout dataset (+ extraction eval set) from synthetic invoices.

python -m docsense_ml.synth.build --out ml/data/synth --n 1000 --aug full --aug-per-image 2
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .augment import augment
from .generator import make_invoice
from .render import CLASSES, Renderer, to_yolo_lines


def _yolo_boxes(regions: list[dict]):
    boxes, labels = [], []
    for line in to_yolo_lines(regions):
        c, cx, cy, w, h = line.split()
        labels.append(int(c))
        boxes.append([float(cx), float(cy), float(w), float(h)])
    return boxes, labels


def _save(img: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).save(path, "JPEG", quality=92)


def _write_labels(path: Path, boxes, labels) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            f"{c} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}"
            for c, b in zip(labels, boxes, strict=True)
        ),
        encoding="utf-8",
    )


def build(
    out: Path,
    n: int,
    seed: int = 0,
    aug: str = "full",
    aug_per_image: int = 1,
    val_every: int = 10,
    start: int = 0,
) -> dict:
    out = Path(out)
    eval_rows = []
    counts = {"train": 0, "val": 0}
    with Renderer() as renderer:
        for i in range(start, start + n):
            inv_seed = seed * 1_000_003 + i
            inv = make_invoice(inv_seed)
            r = renderer.render(inv)
            boxes, labels = _yolo_boxes(r.regions)
            split = "val" if i % val_every == 0 else "train"
            variants = 1 if split == "val" else max(1, aug_per_image)
            for k in range(variants):
                img, bx, lb = augment(r.image, boxes, labels, aug, seed=inv_seed * 31 + k)
                name = f"s{i:06d}_{k}"
                _save(img, out / "images" / split / f"{name}.jpg")
                _write_labels(out / "labels" / split / f"{name}.txt", bx, lb)
                counts[split] += 1
                if split == "val":
                    clean = aug == "none"
                    eval_rows.append(
                        {
                            "id": name,
                            "image": f"../images/val/{name}.jpg",
                            "truth": inv.truth(),
                            # word boxes are only valid for un-augmented images
                            "words": r.words if clean else None,
                            "meta": {
                                "template": inv.template,
                                "category": inv.category,
                                "aug": aug,
                                "fields": r.fields,
                                "regions": r.regions,
                            },
                        }
                    )
    (out / "data.yaml").write_text(
        f"path: {out.resolve().as_posix()}\ntrain: images/train\nval: images/val\n"
        "names:\n" + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)),
        encoding="utf-8",
    )
    ev = out / "eval"
    ev.mkdir(parents=True, exist_ok=True)
    with (ev / "manifest.jsonl").open("w", encoding="utf-8") as fh:
        for row in eval_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ml/data/synth")
    ap.add_argument("--n", type=int, default=200, help="base invoices to render")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--aug", choices=["none", "basic", "full"], default="full")
    ap.add_argument("--aug-per-image", type=int, default=1)
    ap.add_argument("--start", type=int, default=0)
    a = ap.parse_args()
    print(build(Path(a.out), a.n, a.seed, a.aug, a.aug_per_image, start=a.start))


if __name__ == "__main__":
    main()
