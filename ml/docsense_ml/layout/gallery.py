"""Failure/success gallery on real receipts: CORD ground truth (solid) vs model predictions (dashed).

python -m docsense_ml.layout.gallery --weights ml/runs/yolo/exp-c/weights/best.pt
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..synth.render import CLASSES

COLORS = {
    "vendor": "#e11d48",
    "meta": "#2563eb",
    "table": "#16a34a",
    "totals": "#f59e0b",
    "other": "#9333ea",
}
CELL_H = 520


def draw_boxes(img: Image.Image, boxes, dashed: bool) -> None:
    d = ImageDraw.Draw(img)
    W, H = img.size
    for cls, (x0, y0, x1, y1) in boxes:
        c = COLORS[cls]
        rect = [x0 * W, y0 * H, x1 * W, y1 * H]
        if not dashed:
            d.rectangle(rect, outline=c, width=max(3, W // 150))
        else:
            step = 14
            for x in range(int(rect[0]), int(rect[2]), step * 2):
                d.line([(x, rect[1]), (min(x + step, rect[2]), rect[1])], fill=c, width=3)
                d.line([(x, rect[3]), (min(x + step, rect[2]), rect[3])], fill=c, width=3)
            for y in range(int(rect[1]), int(rect[3]), step * 2):
                d.line([(rect[0], y), (rect[0], min(y + step, rect[3]))], fill=c, width=3)
                d.line([(rect[2], y), (rect[2], min(y + step, rect[3]))], fill=c, width=3)
        d.text((rect[0] + 4, rect[1] + 2), cls, fill=c)


def read_gt(label_file: Path):
    out = []
    for line in label_file.read_text().splitlines():
        c, cx, cy, w, h = line.split()
        cx, cy, w, h = map(float, (cx, cy, w, h))
        out.append((CLASSES[int(c)], (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)))
    return out


def main() -> None:
    from ultralytics import YOLO

    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="ml/runs/yolo/exp-c/weights/best.pt")
    ap.add_argument("--real", default="ml/data/cord_layout")
    ap.add_argument("--out", default="docs/images/real_gap.png")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--imgsz", type=int, default=416)
    a = ap.parse_args()
    model = YOLO(a.weights)
    images = sorted((Path(a.real) / "images" / "test").glob("*.png"))[:: max(1, 65 // a.n)][: a.n]
    cells = []
    for p in images:
        gt = read_gt(Path(a.real) / "labels" / "test" / f"{p.stem}.txt")
        res = model.predict(str(p), imgsz=a.imgsz, conf=0.25, device="cpu", verbose=False)[0]
        pred = [
            (model.names[int(c)], tuple(b))
            for c, b in zip(res.boxes.cls.tolist(), res.boxes.xyxyn.tolist(), strict=True)
        ]
        left, right = Image.open(p).convert("RGB"), Image.open(p).convert("RGB")
        draw_boxes(left, gt, dashed=False)
        draw_boxes(right, pred, dashed=True)
        for im in (left, right):
            im.thumbnail((400, CELL_H))
        cells.append((left, right))
    pad = 8
    width = sum(l.width + r.width + pad * 3 for l, r in cells[:3])
    rows = [cells[i : i + 3] for i in range(0, len(cells), 3)]
    row_w = max(sum(l.width + r.width + pad * 3 for l, r in row) for row in rows)
    canvas = Image.new("RGB", (row_w, 30 + len(rows) * (CELL_H + pad)), "#f8fafc")
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    d.text(
        (pad, 6),
        "Real CORD receipts: ground truth (solid) | model prediction (dashed). Only table and totals are annotated.",
        fill="#0f172a",
        font=font,
    )
    y = 30
    for row in rows:
        x = pad
        for left, right in row:
            canvas.paste(left, (x, y))
            canvas.paste(right, (x + left.width + pad, y))
            x += left.width + right.width + pad * 3
        y += CELL_H + pad
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(a.out)
    print("wrote", a.out, canvas.size, "width", width)


if __name__ == "__main__":
    main()
