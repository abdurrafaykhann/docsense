"""'Scene' augmentation: put the document on a large textured surface, like a phone photo.

Real receipts are photographed small in the frame (30-75% of the image) on tables, laps and hands.
The synthetic renders fill the whole frame, which is the main synthetic-to-real gap we measured.
"""

from __future__ import annotations

import cv2
import numpy as np

SURFACES = ["wood", "dark", "fabric", "marble", "skin"]


def surface(h: int, w: int, rng: np.random.Generator) -> np.ndarray:
    """Procedural background: low-frequency colour field + grain + optional wood stripes."""
    kind = SURFACES[int(rng.integers(0, len(SURFACES)))]
    base = {
        "wood": (150, 105, 70), "dark": (38, 36, 40), "fabric": (70, 90, 120),
        "marble": (200, 200, 205), "skin": (205, 160, 135),
    }[kind]  # fmt: skip
    jitter = rng.uniform(0.75, 1.2, size=3)
    colour = np.clip(np.array(base) * jitter, 0, 255).astype(np.float32)
    field = cv2.resize(rng.random((h // 90 + 2, w // 90 + 2)).astype(np.float32), (w, h))
    img = np.empty((h, w, 3), np.float32)
    img[:] = colour
    img *= (0.8 + 0.4 * field)[..., None]
    if kind == "wood":
        stripes = np.sin(np.linspace(0, rng.uniform(25, 60), h))[:, None] * 12
        img += stripes[..., None]
    grain = cv2.GaussianBlur(rng.normal(0, 14, (h, w)).astype(np.float32), (0, 0), 1.5)
    img += grain[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def place_on_scene(
    img: np.ndarray,
    boxes: list[list[float]],
    rng: np.random.Generator,
    min_fill: float = 0.28,
    max_fill: float = 0.8,
) -> tuple[np.ndarray, list[list[float]]]:
    """Paste `img` onto a bigger scene; boxes are YOLO (cx, cy, w, h) normalised and are remapped."""
    h, w = img.shape[:2]
    fill = float(rng.uniform(min_fill, max_fill))  # share of the scene width the page occupies
    W = int(w / fill)
    H = int(max(h / fill * rng.uniform(0.75, 1.0), h * 1.05))
    scene = surface(H, W, rng)
    x0 = int(rng.integers(0, max(1, W - w)))
    y0 = int(rng.integers(0, max(1, H - h)))
    # soft drop shadow so the page sits on the surface
    shadow = np.zeros((H, W), np.float32)
    shadow[y0 + 6 : y0 + h + 6, x0 + 6 : x0 + w + 6] = 1.0
    shadow = cv2.GaussianBlur(shadow, (0, 0), 9)
    scene = (scene * (1 - 0.35 * shadow[..., None])).astype(np.uint8)
    scene[y0 : y0 + h, x0 : x0 + w] = img
    out = []
    for cx, cy, bw, bh in boxes:
        out.append([(x0 + cx * w) / W, (y0 + cy * h) / H, bw * w / W, bh * h / H])
    return scene, out
