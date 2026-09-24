"""Generated stand-ins for real Scans: never commit real family photos to this repo."""

from dataclasses import dataclass

import cv2
import numpy as np

DARK = (25, 25, 28)
WHITE = (242, 242, 240)


@dataclass(frozen=True)
class FakePrint:
    center: tuple[int, int]  # px, (x, y)
    size: tuple[int, int]  # px, (width, height)
    angle: float = 0.0  # degrees, counter-clockwise
    border: bool = False  # classic white border around the image


def _texture(width: int, height: int, rng: np.random.Generator) -> np.ndarray:
    """Photo-like content: a colour gradient plus noise and a few blobs."""
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    base = rng.uniform(40, 200, 3)
    grad = rng.uniform(-60, 60, 3)
    img = base + grad * (xs / width)[..., None] + grad[::-1] * (ys / height)[..., None]
    for _ in range(4):
        cx, cy = rng.integers(0, width), rng.integers(0, height)
        r = int(rng.integers(5, max(6, min(width, height) // 3)))
        cv2.circle(img, (int(cx), int(cy)), r, rng.uniform(0, 255, 3).tolist(), -1)
    img += rng.normal(0, 6, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def make_scan(
    prints: list[FakePrint],
    *,
    shape: tuple[int, int] = (1754, 1275),  # A4 at 150 dpi, (height, width)
    background: tuple[int, int, int] = DARK,
    dust: int = 0,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    height, width = shape
    scan = np.empty((height, width, 3), np.float32)
    scan[:] = background
    scan += rng.normal(0, 2, scan.shape)
    scan = np.clip(scan, 0, 255).astype(np.uint8)

    for p in prints:
        w, h = p.size
        content = _texture(w, h, rng)
        if p.border:
            b = max(4, min(w, h) // 20)
            content[:b], content[-b:], content[:, :b], content[:, -b:] = 250, 250, 250, 250
        # Paste the (possibly rotated) print through a mask.
        m = cv2.getRotationMatrix2D((w / 2, h / 2), p.angle, 1.0)
        m[0, 2] += p.center[0] - w / 2
        m[1, 2] += p.center[1] - h / 2
        warped = cv2.warpAffine(content, m, (width, height), flags=cv2.INTER_LINEAR)
        mask = cv2.warpAffine(np.full((h, w), 255, np.uint8), m, (width, height))
        scan[mask > 127] = warped[mask > 127]

    for _ in range(dust):
        x, y = int(rng.integers(0, width)), int(rng.integers(0, height))
        cv2.circle(scan, (x, y), int(rng.integers(1, 4)), (230, 230, 230), -1)
    return scan
