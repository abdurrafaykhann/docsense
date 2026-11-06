"""Make clean renders look like phone photos (Albumentations, bbox-aware).

Levels:  none | basic (geometry + blur + jpeg) | full (adds paper texture, shadows, low light,
creases, stains, desk background, partial crops).
"""

from __future__ import annotations

import albumentations as A
import cv2
import numpy as np

# ---- custom image-only transforms ---------------------------------------------------------


class PaperTexture(A.ImageOnlyTransform):
    """Multiply by low-frequency paper grain + fine fibres, tinted slightly warm."""

    def __init__(self, strength=(0.04, 0.14), p=0.7):
        super().__init__(p=p)
        self.strength = strength

    def apply(self, img, strength=0.08, seed=0, **params):
        rng = np.random.default_rng(seed)
        h, w = img.shape[:2]
        coarse = cv2.resize(rng.random((h // 24 + 2, w // 24 + 2)).astype(np.float32), (w, h))
        fine = rng.normal(0, 1, (h, w)).astype(np.float32)
        tex = 1 - strength * (0.7 * coarse + 0.3 * np.clip(fine, -2, 2) / 2)
        tint = np.array([1.0, 0.985, 0.95], dtype=np.float32)
        out = img.astype(np.float32) * tex[..., None] * tint
        return np.clip(out, 0, 255).astype(np.uint8)

    def get_params(self):
        return {
            "strength": float(self.random_generator.uniform(*self.strength)),
            "seed": int(self.random_generator.integers(0, 2**31 - 1)),
        }

    def get_transform_init_args_names(self):
        return ("strength",)


class Creases(A.ImageOnlyTransform):
    """1-3 soft fold lines: a dark/light pair of blurred strokes across the page."""

    def __init__(self, p=0.35):
        super().__init__(p=p)

    def apply(self, img, lines=(), **params):
        h, w = img.shape[:2]
        layer = np.zeros((h, w), np.float32)
        for x0, y0, x1, y1, sign in lines:
            cv2.line(layer, (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h)), sign, 3)
        layer = cv2.GaussianBlur(layer, (0, 0), 3)
        out = img.astype(np.float32) * (1 + 0.28 * layer)[..., None]
        return np.clip(out, 0, 255).astype(np.uint8)

    def get_params(self):
        rnd = self.random_generator.uniform
        lines = []
        for _ in range(int(self.random_generator.integers(1, 4))):
            horizontal = self.random_generator.random() < 0.5
            a, b = rnd(0.1, 0.9), rnd(0.1, 0.9)
            coords = (0.0, a, 1.0, b) if horizontal else (a, 0.0, b, 1.0)
            lines.append((*coords, -1.0))
            off = 0.004
            lines.append(
                (
                    coords[0] + (0 if horizontal else off),
                    coords[1] + (off if horizontal else 0),
                    coords[2] + (0 if horizontal else off),
                    coords[3] + (off if horizontal else 0),
                    0.8,
                )
            )
        return {"lines": lines}

    def get_transform_init_args_names(self):
        return ()


class Stains(A.ImageOnlyTransform):
    """Coffee / grease blobs: soft brownish ellipses, alpha-blended."""

    def __init__(self, p=0.3):
        super().__init__(p=p)

    def apply(self, img, blobs=(), **params):
        h, w = img.shape[:2]
        out = img.astype(np.float32)
        for cx, cy, rx, ry, ang, alpha in blobs:
            mask = np.zeros((h, w), np.float32)
            cv2.ellipse(
                mask, (int(cx * w), int(cy * h)), (int(rx * w), int(ry * h)), ang, 0, 360, 1.0, -1
            )
            mask = cv2.GaussianBlur(mask, (0, 0), 0.02 * min(h, w) + 1) * alpha
            tint = np.array([120, 85, 50], np.float32)
            out = out * (1 - mask[..., None]) + out * (tint / 255.0) * mask[..., None]
        return np.clip(out, 0, 255).astype(np.uint8)

    def get_params(self):
        r = self.random_generator.uniform
        blobs = [
            (r(0.1, 0.9), r(0.1, 0.9), r(0.03, 0.12), r(0.03, 0.12), r(0, 180), r(0.25, 0.6))
            for _ in range(int(self.random_generator.integers(1, 4)))
        ]
        return {"blobs": blobs}

    def get_transform_init_args_names(self):
        return ()


class LowLight(A.ImageOnlyTransform):
    """Dim exposure with a vignette and a colour cast (indoor tungsten / dusk)."""

    def __init__(self, p=0.3):
        super().__init__(p=p)

    def apply(self, img, gain=0.6, cast=(1.0, 0.95, 0.85), vig=0.5, **params):
        h, w = img.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / 1.414
        v = 1 - vig * d**2
        out = img.astype(np.float32) * gain * v[..., None] * np.array(cast, np.float32)
        return np.clip(out, 0, 255).astype(np.uint8)

    def get_params(self):
        r = self.random_generator.uniform
        return {"gain": r(0.35, 0.75), "vig": r(0.2, 0.7), "cast": (1.0, r(0.88, 1.0), r(0.7, 1.0))}

    def get_transform_init_args_names(self):
        return ()


class DeskBackground(A.ImageOnlyTransform):
    """Pad with a wooden/desk-like coloured textured border (page photographed on a table)."""

    def __init__(self, p=0.6):
        super().__init__(p=p)

    def apply(self, img, pad=0.08, color=(90, 70, 55), seed=0, **params):
        h, w = img.shape[:2]
        py, px = int(h * pad), int(w * pad)
        rng = np.random.default_rng(seed)
        bg = np.empty((h + 2 * py, w + 2 * px, 3), np.float32)
        bg[:] = color
        noise = cv2.GaussianBlur(rng.normal(0, 18, bg.shape[:2]).astype(np.float32), (0, 0), 4)
        bg += noise[..., None]
        bg[py : py + h, px : px + w] = img
        return np.clip(bg, 0, 255).astype(np.uint8)

    def get_params(self):
        r = self.random_generator.uniform
        base = int(self.random_generator.integers(0, 3))
        color = [(95, 72, 55), (60, 60, 64), (170, 160, 140)][base]
        return {
            "pad": r(0.03, 0.12),
            "color": color,
            "seed": int(self.random_generator.integers(0, 2**31 - 1)),
        }

    def get_transform_init_args_names(self):
        return ()


def _bbox_params():
    return A.BboxParams(
        format="yolo", label_fields=["labels"], min_visibility=0.3, clip=True, min_area=16
    )


Spec = tuple[float, "callable"]  # (probability, factory -> transform with p=1)


def specs(level: str) -> list[Spec]:
    """(probability, factory) pairs. Each transform is gated and seeded individually by augment()
    because Albumentations' Compose(seed=...) correlates the per-transform draws."""
    if level == "none":
        return []
    geometry: list[Spec] = [
        (0.7, lambda: A.Perspective(scale=(0.02, 0.07), fill=(235, 235, 235), p=1.0)),
        (
            0.8,
            lambda: A.Rotate(
                limit=12, border_mode=cv2.BORDER_CONSTANT, fill=(235, 235, 235), p=1.0
            ),
        ),
    ]
    quality: list[Spec] = [
        (
            0.5,
            lambda: A.OneOf(
                [A.GaussianBlur(blur_limit=(3, 7)), A.MotionBlur(blur_limit=(3, 9))], p=1.0
            ),
        ),
        (0.4, lambda: A.GaussNoise(std_range=(0.02, 0.08), p=1.0)),
        (0.8, lambda: A.ImageCompression(quality_range=(30, 90), p=1.0)),
    ]
    if level == "basic":
        return [*geometry, *quality]
    photometric: list[Spec] = [
        (0.7, lambda: PaperTexture(p=1.0)),
        (0.35, lambda: Creases(p=1.0)),
        (0.3, lambda: Stains(p=1.0)),
        (
            0.5,
            lambda: A.RandomShadow(
                shadow_roi=(0, 0, 1, 1), num_shadows_limit=(1, 2), shadow_dimension=5, p=1.0
            ),
        ),
        (
            0.6,
            lambda: A.RandomBrightnessContrast(
                brightness_limit=(-0.25, 0.2), contrast_limit=(-0.3, 0.2), p=1.0
            ),
        ),
        (0.4, lambda: A.RandomGamma(gamma_limit=(70, 140), p=1.0)),
        (0.3, lambda: LowLight(p=1.0)),
        (0.6, lambda: DeskBackground(p=1.0)),
    ]
    return [*photometric, *geometry, *quality]


def _apply(factory, img, boxes, labels, seed: int):
    tf = A.Compose([factory()], bbox_params=_bbox_params(), seed=seed)
    out = tf(image=img, bboxes=boxes, labels=labels)
    return out["image"], [list(b) for b in out["bboxes"]], [int(x) for x in out["labels"]]


def partial_crop(img: np.ndarray, boxes: list[list[float]], labels: list[int], rng) -> tuple:
    """Crop away up to ~12% from each side (a cropped photo), keeping boxes consistent."""
    h, w = img.shape[:2]
    x0, t = int(w * rng.uniform(0, 0.12)), int(h * rng.uniform(0, 0.12))
    r, b = w - int(w * rng.uniform(0, 0.12)), h - int(h * rng.uniform(0, 0.12))
    return _apply(lambda: A.Crop(x_min=x0, y_min=t, x_max=r, y_max=b), img, boxes, labels, 1)


def augment(
    img: np.ndarray, boxes_yolo: list[list[float]], labels: list[int], level: str, seed: int
) -> tuple[np.ndarray, list[list[float]], list[int]]:
    """Apply the pipeline; boxes are YOLO (cx, cy, w, h) normalised. Deterministic per seed."""
    if level == "none":
        return img, boxes_yolo, labels
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    image, boxes, lab = img, boxes_yolo, labels
    applied = 0
    for prob, factory in specs(level):
        if rng.random() < prob:
            image, boxes, lab = _apply(factory, image, boxes, lab, int(rng.integers(0, 2**31 - 1)))
            applied += 1
    if applied == 0:  # every sample is at least re-encoded like a phone photo
        image, boxes, lab = _apply(
            lambda: A.ImageCompression(quality_range=(40, 85), p=1.0),
            image,
            boxes,
            lab,
            int(rng.integers(0, 2**31 - 1)),
        )
    if level == "full" and rng.random() < 0.3 and boxes:
        image, boxes, lab = partial_crop(image, boxes, lab, rng)
    return image, boxes, lab
