"""Build YOLO layout datasets (one per augmentation level) from the same synthetic invoices.

    python -m docsense_ml.synth.build --out ml/data/synth --n 600

Layout of --out:
    none/ basic/ full/       <level>/images/{train,val}, labels/{train,val}, data.yaml
    valfull/                 the shared validation invoices at 'full' augmentation (hard domain)
    eval/ evalfull/          extraction eval sets (manifest.jsonl): clean+oracle words / augmented
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

LEVELS = ("none", "basic", "full")


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


def write_data_yaml(root: Path, train: str = "images/train", val: str = "images/val") -> None:
    (root / "data.yaml").write_text(
        f"path: {root.resolve().as_posix()}\ntrain: {train}\nval: {val}\nnames:\n"
        + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)),
        encoding="utf-8",
    )


def _write_manifest(directory: Path, rows: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "manifest.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def build(
    out: Path,
    n: int,
    seed: int = 0,
    levels: tuple[str, ...] = LEVELS,
    val_every: int = 10,
    start: int = 0,
) -> dict:
    out = Path(out)
    counts = {f"{lvl}/{s}": 0 for lvl in levels for s in ("train", "val")}
    counts["valfull"] = 0
    eval_clean, eval_full = [], []
    with Renderer() as renderer:
        for i in range(start, start + n):
            inv_seed = seed * 1_000_003 + i
            inv = make_invoice(inv_seed)
            r = renderer.render(inv)
            boxes, labels = _yolo_boxes(r.regions)
            split = "val" if i % val_every == 0 else "train"
            name = f"s{i:06d}"
            meta = {"template": inv.template, "category": inv.category, "fields": r.fields}
            for lvl in levels:
                img, bx, lb = augment(r.image, boxes, labels, lvl, seed=inv_seed * 31 + 1)
                root = out / lvl
                _save(img, root / "images" / split / f"{name}.jpg")
                _write_labels(root / "labels" / split / f"{name}.txt", bx, lb)
                counts[f"{lvl}/{split}"] += 1
            if split == "val":
                img, bx, lb = augment(r.image, boxes, labels, "full", seed=inv_seed * 31 + 2)
                _save(img, out / "valfull" / "images" / "val" / f"{name}.jpg")
                _write_labels(out / "valfull" / "labels" / "val" / f"{name}.txt", bx, lb)
                counts["valfull"] += 1
                eval_clean.append(
                    {
                        "id": name,
                        "image": f"../none/images/val/{name}.jpg",
                        "truth": inv.truth(),
                        "words": r.words,  # oracle OCR: valid only for the clean render
                        "meta": {**meta, "aug": "none", "regions": r.regions},
                    }
                )
                eval_full.append(
                    {
                        "id": name,
                        "image": f"../valfull/images/val/{name}.jpg",
                        "truth": inv.truth(),
                        "words": None,
                        "meta": {**meta, "aug": "full"},
                    }
                )
    for lvl in levels:
        write_data_yaml(out / lvl)
    write_data_yaml(out / "valfull", train="images/val", val="images/val")
    _write_manifest(out / "eval", eval_clean)
    _write_manifest(out / "evalfull", eval_full)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ml/data/synth")
    ap.add_argument("--n", type=int, default=200, help="base invoices to render")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--levels", default=",".join(LEVELS))
    ap.add_argument("--start", type=int, default=0)
    a = ap.parse_args()
    print(build(Path(a.out), a.n, a.seed, tuple(a.levels.split(",")), start=a.start))


if __name__ == "__main__":
    main()
