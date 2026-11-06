"""Real-receipt layout labels derived from CORD's own word-level annotations.

CORD annotates every word of `menu.*`, `sub_total.*` and `total.*` with a quad. The union of those
quads gives genuine human-annotated boxes for two of our five classes:
    table  <- menu.*            totals <- sub_total.* + total.*
CORD does NOT annotate store name, date, invoice number or footer: vendor, meta and other have no
real ground truth here (hand-label them with ml/tools/labeler.html, see README).

Split (deterministic): the first TUNE receipts are for few-shot mixing (experiment d); the rest are
the held-out real TEST set.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from ..synth.build import write_data_yaml

TABLE, TOTALS = 2, 3
TUNE = 30
PAD = 0.006


def quads_to_box(quads: list[dict], w: int, h: int) -> list[float] | None:
    xs, ys = [], []
    for q in quads:
        xs += [q[f"x{i}"] for i in range(1, 5)]
        ys += [q[f"y{i}"] for i in range(1, 5)]
    if not xs:
        return None
    if (max(xs) - min(xs)) / w <= 0.01 or (max(ys) - min(ys)) / h <= 0.005:
        return None  # degenerate before padding
    x0, x1 = max(0.0, min(xs) / w - PAD), min(1.0, max(xs) / w + PAD)
    y0, y1 = max(0.0, min(ys) / h - PAD), min(1.0, max(ys) / h + PAD)
    return [(x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0]  # YOLO cx cy w h


def cord_layout_boxes(valid_line: list[dict], w: int, h: int) -> list[tuple[int, list[float]]]:
    groups: dict[int, list[dict]] = {TABLE: [], TOTALS: []}
    for line in valid_line:
        cat = line["category"]
        cls = (
            TABLE
            if cat.startswith("menu.")
            else TOTALS
            if cat.startswith(("sub_total", "total"))
            else None
        )
        if cls is not None:
            groups[cls] += [wd["quad"] for wd in line["words"]]
    out = []
    for cls, quads in groups.items():
        box = quads_to_box(quads, w, h)
        if box:
            out.append((cls, box))
    return out


def build_real_layout(parquet: Path, cord_dir: Path, out: Path) -> dict:
    """Labels aligned with the converted CORD set (same filter/order as cord.convert)."""
    import pyarrow.parquet as pq

    from ..cord import cord_truth

    out = Path(out)
    for split in ("tune", "test"):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
    idx = 0
    counts = {"tune": 0, "test": 0}
    for batch in pq.ParquetFile(parquet).iter_batches(batch_size=8):
        for rec in batch.to_pylist():
            gt = json.loads(rec["ground_truth"])
            if "total" not in cord_truth(gt.get("gt_parse", {})):
                continue
            name = f"cord_{idx:04d}"
            src = cord_dir / "images" / f"{name}.png"
            idx += 1
            if not src.exists():
                continue
            w, h = Image.open(src).size
            boxes = cord_layout_boxes(gt.get("valid_line", []), w, h)
            if not boxes:
                continue
            split = "tune" if counts["tune"] < TUNE else "test"
            shutil.copy(src, out / "images" / split / f"{name}.png")
            (out / "labels" / split / f"{name}.txt").write_text(
                "\n".join(f"{c} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}" for c, b in boxes),
                encoding="utf-8",
            )
            counts[split] += 1
    write_data_yaml(out, train="images/tune", val="images/test")
    return counts


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--cord", default="ml/data/cord")
    ap.add_argument("--out", default="ml/data/cord_layout")
    a = ap.parse_args()
    print(
        build_real_layout(Path(a.cord) / "_raw" / "cord-v2-test.parquet", Path(a.cord), Path(a.out))
    )
