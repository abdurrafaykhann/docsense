"""Image cleanup for phone photos and scans: deskew, denoise, contrast. NumPy RGB in/out."""

from __future__ import annotations

import cv2
import numpy as np

MAX_SIDE = 2200  # longest side after loading; keeps OCR fast on CPU


def limit_size(img: np.ndarray, max_side: int = MAX_SIDE) -> np.ndarray:
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return img
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _rotate(img: np.ndarray, angle: float, border) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=border
    )


def estimate_skew(gray: np.ndarray, max_angle: float = 15.0) -> float:
    """Skew angle in degrees (positive = text runs counter-clockwise) via projection profile.

    Text lines make the row-sum histogram spiky when the page is level; we search the angle
    that maximises its variance (coarse 1 degree, then 0.1 degree refinement).
    """
    small = gray
    if max(gray.shape) > 700:
        s = 700 / max(gray.shape)
        small = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    def score(a: float) -> float:
        return float(np.var(_rotate(binary, a, 0).sum(axis=1, dtype=np.float64)))

    coarse = max(np.arange(-max_angle, max_angle + 0.01, 1.0), key=score)
    fine = max(np.arange(coarse - 1, coarse + 1.01, 0.1), key=score)
    return float(fine)


def deskew(img: np.ndarray) -> tuple[np.ndarray, float]:
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    angle = estimate_skew(gray)
    if abs(angle) < 0.3:
        return img, 0.0
    return _rotate(img, angle, (255, 255, 255)), angle


def enhance(img: np.ndarray) -> np.ndarray:
    """Light denoise + CLAHE on luminance (keeps colours for stamps/logos)."""
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    l_chan = cv2.fastNlMeansDenoising(
        lab[:, :, 0], None, h=5, templateWindowSize=7, searchWindowSize=15
    )
    l_chan = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l_chan)
    lab[:, :, 0] = l_chan
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def clean_image(img: np.ndarray) -> tuple[np.ndarray, dict]:
    img = limit_size(img)
    img, angle = deskew(img)
    img = enhance(img)
    return img, {"deskew_deg": round(angle, 1), "size": [img.shape[1], img.shape[0]]}
