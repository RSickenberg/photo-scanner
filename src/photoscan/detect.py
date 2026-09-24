"""Find the Prints on a Scan and cut each one out, straightened."""

from dataclasses import dataclass

import cv2
import numpy as np

# Detection runs on a downscaled copy: plenty to find photo edges, much faster.
_DETECT_LONG_SIDE = 1200
# Colour distance (Lab) from the background above which a pixel is "not glass".
# Adaptive to the background's own noise, never below _MIN_CONTRAST. Low on
# purpose: Polaroid frames on the white lid sit only ~12 units away (measured on
# a real LiDE 400 Scan, lid noise p99 ~3).
_MIN_CONTRAST = 8.0
_NOISE_FACTOR = 2.5


@dataclass(frozen=True)
class Region:
    """Where one Print sits on a Scan, in full-resolution pixels."""

    center: tuple[float, float]  # (x, y)
    size: tuple[float, float]  # (width, height), as the Print is oriented on the glass
    angle: float  # degrees, as returned by cv2.minAreaRect, normalised to [-45, 45)


def find_prints(scan: np.ndarray, dpi: int, *, min_side_cm: float = 2.5) -> list[Region]:
    """Every Print on the Scan, in reading order (top-to-bottom, then left-to-right)."""
    small, scale = _downscale(_to_8bit(scan))
    mask = _foreground_mask(small)

    min_side_px = min_side_cm / 2.54 * dpi * scale
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    for contour in contours:
        (cx, cy), (w, h), angle = cv2.minAreaRect(contour)
        if min(w, h) < min_side_px:
            continue
        regions.append(_normalise(cx / scale, cy / scale, w / scale, h / scale, angle))

    return _reading_order(regions)


def cut(scan: np.ndarray, region: Region, *, inset_px: int = 2) -> np.ndarray:
    """The Print inside `region`, rotated upright, trimmed `inset_px` inside its edge."""
    (cx, cy), (w, h) = region.center, region.size
    rotation = cv2.getRotationMatrix2D((cx, cy), region.angle, 1.0)
    # Shift so the Print lands centred in an output of exactly its own size.
    rotation[0, 2] += w / 2 - cx
    rotation[1, 2] += h / 2 - cy
    upright = cv2.warpAffine(
        scan, rotation, (round(w), round(h)), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )
    if inset_px:
        upright = upright[inset_px:-inset_px, inset_px:-inset_px]
    return upright


def _to_8bit(scan: np.ndarray) -> np.ndarray:
    return (scan >> 8).astype(np.uint8) if scan.dtype == np.uint16 else scan


def _downscale(img: np.ndarray) -> tuple[np.ndarray, float]:
    scale = min(1.0, _DETECT_LONG_SIDE / max(img.shape[:2]))
    if scale < 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img, scale


def _foreground_mask(img: np.ndarray) -> np.ndarray:
    """White where something differs from the glass/lid background."""
    # Median, not Gaussian: removes noise without smearing edges outwards, which a
    # low threshold would otherwise count as part of the Print.
    lab = cv2.cvtColor(cv2.medianBlur(img, 5), cv2.COLOR_RGB2LAB).astype(np.float32)
    background, noise = _background(lab)
    distance = np.linalg.norm(lab - background, axis=-1)
    distance = np.clip(distance, 0, 255).astype(np.uint8)

    # Not Otsu: a high-contrast photo drags Otsu's split far above pale frames
    # and skies, which then get cut off as if they were background.
    threshold = max(_MIN_CONTRAST, _NOISE_FACTOR * noise)
    _, mask = cv2.threshold(distance, threshold, 255, cv2.THRESH_BINARY)

    # Close gaps where a Print is locally close to the background colour
    # (dark sky on a dark cloth), then drop specks and thin slivers, like the
    # scanner's vignetting along the glass edge, that would stretch a Print's box.
    close = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close, iterations=2)
    open_ = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_)


def _background(lab: np.ndarray) -> tuple[np.ndarray, float]:
    """Most common colour along the Scan's outer edge, and how much it varies.

    The mode, not the mean: Prints pushed against the glass edge cover part of
    it, but the background still wins as long as it shows along most of it.
    """
    border = np.concatenate(
        [
            lab[:4].reshape(-1, 3),
            lab[-4:].reshape(-1, 3),
            lab[:, :4].reshape(-1, 3),
            lab[:, -4:].reshape(-1, 3),
        ]
    )
    quantised = (border // 8).astype(np.int32)
    keys, counts = np.unique(quantised, axis=0, return_counts=True)
    winner = keys[counts.argmax()]
    pixels = border[(quantised == winner).all(axis=1)]
    colour = pixels.mean(axis=0)
    noise = float(np.percentile(np.linalg.norm(pixels - colour, axis=-1), 99))
    return colour, noise


def _normalise(cx: float, cy: float, w: float, h: float, angle: float) -> Region:
    """Pick the smallest rotation that straightens the Print.

    minAreaRect may report a 3° tilt as (h, w, 93°) or (w, h, -87°): fold the
    angle into [-45, 45) and swap sides accordingly, so a landscape Print stays
    landscape.
    """
    while angle >= 45:
        angle -= 90
        w, h = h, w
    while angle < -45:
        angle += 90
        w, h = h, w
    return Region(center=(cx, cy), size=(w, h), angle=angle)


def _reading_order(regions: list[Region]) -> list[Region]:
    """Group into rows (centres within half the shortest Print's height), then left-to-right."""
    if not regions:
        return []
    band = min(min(r.size) for r in regions) / 2
    rows: list[list[Region]] = []
    for region in sorted(regions, key=lambda r: r.center[1]):
        if rows and region.center[1] - rows[-1][0].center[1] <= band:
            rows[-1].append(region)
        else:
            rows.append([region])
    return [r for row in rows for r in sorted(row, key=lambda r: r.center[0])]
