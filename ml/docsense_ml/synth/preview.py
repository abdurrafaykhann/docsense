"""Before/after grid: clean render vs basic vs full augmentation, with region boxes drawn.

python -m docsense_ml.synth.preview --out docs/images/augmentation.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .augment import augment
from .build import _yolo_boxes
from .generator import TEMPLATES, make_invoice
from .render import CLASSES, Renderer

COLORS = ["#e11d48", "#2563eb", "#16a34a", "#f59e0b", "#9333ea"]
CELL = 360


def draw(img: np.ndarray, boxes, labels) -> Image.Image:
    im = Image.fromarray(img).convert("RGB")
    d = ImageDraw.Draw(im)
    W, H = im.size
    for (cx, cy, w, h), c in zip(boxes, labels, strict=True):
        d.rectangle(
            [(cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H],
            outline=COLORS[c],
            width=max(2, W // 300),
        )
    im.thumbnail((CELL, CELL * 1.4))
    return im


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/images/augmentation.png")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    levels = ["none", "basic", "full"]
    rows = []
    with Renderer() as renderer:
        for i, tpl in enumerate(TEMPLATES):
            inv = make_invoice(a.seed * 100 + i, tpl)
            r = renderer.render(inv)
            boxes, labels = _yolo_boxes(r.regions)
            rows.append(
                [draw(*augment(r.image, boxes, labels, lv, seed=a.seed + i)[:3]) for lv in levels]
            )
    pad, head = 10, 34
    colw = [max(r[j].width for r in rows) for j in range(3)]
    rowh = [max(im.height for im in r) for r in rows]
    canvas = Image.new(
        "RGB", (sum(colw) + pad * 4, head + sum(rowh) + pad * (len(rows) + 1)), "#f8fafc"
    )
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    x = pad
    for j, title in enumerate(
        ["Clean render (labels from DOM)", "Basic augmentation", "Full augmentation"]
    ):
        d.text((x, 6), title, fill="#0f172a", font=font)
        x += colw[j] + pad
    y = head
    for r, h in zip(rows, rowh, strict=True):
        x = pad
        for j, im in enumerate(r):
            canvas.paste(im, (x, y))
            x += colw[j] + pad
        y += h + pad
    legend = "  ".join(f"{c}" for c in CLASSES)
    d.text((pad, canvas.height - 24), f"classes: {legend}", fill="#475569", font=font)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(a.out)
    print("wrote", a.out, canvas.size)


if __name__ == "__main__":
    main()
