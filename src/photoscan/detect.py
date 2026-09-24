"""Find the Prints on a Scan, cut each one out straightened, repair glass dust.

A Calibration, made from a Scan of the empty glass, makes this more precise:
Prints are found against that exact background (vignetting, lid streaks and
all) instead of a single colour guessed from the Scan's border, and specks of
dust on the glass are known and repaired in every Extract.
"""

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
# Glass dust: specks up to this size (mm, longest side) that stand out from
# their surroundings by more than _DUST_MIN_CONTRAST grey levels.
_DUST_MAX_MM = 1.5
_DUST_MIN_CONTRAST = 12.0
# A calibrated speck is repaired only where the Extract shows the same pattern
# (correlation of speck contrast). Measured on a real lid: lint projected onto
# real Polaroids scored p99 0.48, and only 1 of 498 exceeded 0.6.
_DUST_MIN_MATCH = 0.6


@dataclass(frozen=True)
class Region:
    """Where one Print sits on a Scan, in full-resolution pixels."""

    center: tuple[float, float]  # (x, y)
    size: tuple[float, float]  # (width, height), as the Print is oriented on the glass
    angle: float  # degrees, as returned by cv2.minAreaRect, normalised to [-45, 45)


@dataclass(frozen=True, eq=False)
class Calibration:
    """What the empty glass looks like, from one Scan of it."""

    reference: np.ndarray  # downscaled, Lab (float32)
    colour: tuple[float, float, float]  # mean background colour, Lab
    noise: float  # p99 pixel noise of the background, Lab distance
    dust: np.ndarray  # full-resolution bool mask of specks on the glass (or the lid)
    dust_specks: int
    dpi: int
    contrast: np.ndarray  # full-resolution speck contrast (uint8), to match against Extracts

    @property
    def threshold(self) -> float:
        return max(_MIN_CONTRAST, _NOISE_FACTOR * self.noise)


def calibrate(empty: np.ndarray, dpi: int) -> Calibration:
    """Learn the background and the glass dust from a Scan of the empty glass."""
    empty8 = _to_8bit(empty)
    reference = _lab(_downscale(empty8)[0])
    # Noise = what's left once slow shading (vignetting, lid gradient) is removed.
    # Comparing two Scans adds two such noises, hence the sqrt(2).
    shading = cv2.GaussianBlur(reference, (0, 0), 15)
    single = _robust_p99(np.linalg.norm(reference - shading, axis=-1))
    contrast = _speck_contrast(cv2.cvtColor(empty8, cv2.COLOR_RGB2GRAY), dpi)
    dust, specks = _find_dust(contrast, dpi)
    return Calibration(
        reference=reference,
        colour=tuple(float(c) for c in reference.reshape(-1, 3).mean(axis=0)),
        noise=float(single * np.sqrt(2)),
        dust=dust,
        dust_specks=specks,
        dpi=dpi,
        contrast=contrast,
    )


def find_prints(
    scan: np.ndarray,
    dpi: int,
    *,
    min_side_cm: float = 2.5,
    calibration: Calibration | None = None,
) -> list[Region]:
    """Every Print on the Scan, in reading order (top-to-bottom, then left-to-right)."""
    small, scale = _downscale(_to_8bit(scan))
    mask = _foreground_mask(small, calibration)

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
    return _upright(scan, region, inset_px, cv2.INTER_CUBIC)


def repair_dust(
    extract: np.ndarray, calibration: Calibration, region: Region, *, inset_px: int = 2
) -> tuple[np.ndarray, int]:
    """Fill in the glass dust visible on this Extract; returns (image, specks repaired).

    The empty-glass Scan can't tell dust on the glass from lint on the lid: lid
    lint ends up behind the Print and doesn't show. So a calibrated speck is
    only repaired where the Extract shows that same speck: same place, same shape.
    """
    known = _upright(calibration.dust.astype(np.uint8) * 255, region, inset_px, cv2.INTER_NEAREST)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(known)
    if count == 1:
        return extract, 0
    expected = _upright(calibration.contrast, region, inset_px, cv2.INTER_LINEAR)
    found = _speck_contrast(cv2.cvtColor(_to_8bit(extract), cv2.COLOR_RGB2GRAY), calibration.dpi)
    limit = _speck_limit(found)
    shown = []
    for i in range(1, count):
        x, y, w, h = stats[i, :4]
        seen, want = found[y : y + h, x : x + w], expected[y : y + h, x : x + w]
        if (seen[labels[y : y + h, x : x + w] == i] > limit).any() and _match(seen, want):
            shown.append(i)
    dust = np.isin(labels, shown).astype(np.uint8) * 255
    specks = len(shown)
    if not specks:
        return extract, 0
    if extract.dtype == np.uint8:
        return cv2.inpaint(extract, dust, 3, cv2.INPAINT_TELEA), specks
    # OpenCV inpaints 16-bit images one channel at a time only.
    channels = [cv2.inpaint(extract[..., c], dust, 3, cv2.INPAINT_TELEA) for c in range(3)]
    return np.dstack(channels), specks


def match_backs(
    fronts: list[Region], backs: list[Region], dpi: int, *, tolerance_cm: float = 3.0
) -> tuple[dict[int, int], list[int]]:
    """Pair each Back with the front it belongs to: {front index: back index}.

    Prints are flipped in place, so a Back lies roughly where its front was,
    same size (sides maybe swapped). Tolerates moving up to `tolerance_cm` and
    any turn. Sizes must agree within 10%, which also tells swapped Prints of
    different sizes apart. Returns the pairs and the Backs left unmatched.
    """
    tolerance_px = tolerance_cm / 2.54 * dpi
    candidates = []
    for f, front in enumerate(fronts):
        for b, back in enumerate(backs):
            distance = float(np.hypot(*np.subtract(front.center, back.center)))
            sizes = np.divide(sorted(back.size), sorted(front.size))
            if distance <= tolerance_px and np.all(np.abs(sizes - 1) <= 0.10):
                candidates.append((distance, f, b))
    pairs: dict[int, int] = {}
    for _, f, b in sorted(candidates):  # closest pairs first
        if f not in pairs and b not in pairs.values():
            pairs[f] = b
    unmatched = [b for b in range(len(backs)) if b not in pairs.values()]
    return pairs, unmatched


def _upright(image: np.ndarray, region: Region, inset_px: int, interpolation: int) -> np.ndarray:
    (cx, cy), (w, h) = region.center, region.size
    rotation = cv2.getRotationMatrix2D((cx, cy), region.angle, 1.0)
    # Shift so the Print lands centred in an output of exactly its own size.
    rotation[0, 2] += w / 2 - cx
    rotation[1, 2] += h / 2 - cy
    upright = cv2.warpAffine(
        image, rotation, (round(w), round(h)), flags=interpolation, borderMode=cv2.BORDER_REPLICATE
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


def _lab(img: np.ndarray) -> np.ndarray:
    # Median, not Gaussian: removes noise without smearing edges outwards, which a
    # low threshold would otherwise count as part of the Print.
    return cv2.cvtColor(cv2.medianBlur(img, 5), cv2.COLOR_RGB2LAB).astype(np.float32)


def _foreground_mask(img: np.ndarray, calibration: Calibration | None) -> np.ndarray:
    """White where something differs from the glass/lid background."""
    lab = _lab(img)
    background, noise = _background(lab)
    unlike_lid = np.linalg.norm(lab - background, axis=-1)
    if calibration is None:
        # Not Otsu: a high-contrast photo drags Otsu's split far above pale frames
        # and skies, which then get cut off as if they were background.
        mask = unlike_lid > max(_MIN_CONTRAST, _NOISE_FACTOR * noise)
    else:
        reference = calibration.reference
        if reference.shape != lab.shape:  # calibrated at another dpi
            reference = cv2.resize(reference, lab.shape[1::-1], interpolation=cv2.INTER_AREA)
        # A Print must differ from the empty glass AND from the Scan's own
        # background colour. The reference alone isn't enough: Prints (thick
        # Polaroids especially) lift the lid, which then shades the gaps between
        # them a little differently than during calibration, enough to join two
        # Prints 2.5 mm apart (real LiDE 400 Scan, 2026-09-24). The colour test
        # rejects that shade; the reference test rejects edge vignetting and lint.
        unlike_glass = np.linalg.norm(lab - reference, axis=-1) > calibration.threshold
        mask = unlike_glass & (unlike_lid > _MIN_CONTRAST)
    return _clean(mask.astype(np.uint8) * 255)


def _clean(mask: np.ndarray) -> np.ndarray:
    """Close gaps inside Prints, then drop specks and thin slivers.

    Closing fills spots where a Print is locally close to the background (dark
    sky on a dark cloth). Outside the Scan counts as background, so a Print a
    few mm from the glass edge isn't bridged to it; OR-ing the raw mask back
    restores what that erodes off Prints that do touch the edge. Opening then
    drops specks and slivers (vignetting along the glass edge) that would
    stretch a Print's box.
    """
    close = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, close, iterations=2, borderType=cv2.BORDER_CONSTANT, borderValue=0
    )
    mask = closed | mask
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


def _robust_p99(values: np.ndarray) -> float:
    """p99 of the noise, from its p90: dust or lint (the top ~1-5%) can't inflate it.

    For Rayleigh-distributed noise magnitudes, p99 / p90 = 1.41.
    """
    return float(np.percentile(values, 90) * 1.41)


def _speck_contrast(gray: np.ndarray, dpi: int) -> np.ndarray:
    """How much each pixel stands out from its immediate surroundings (uint8)."""
    max_px = _DUST_MAX_MM / 25.4 * dpi
    return cv2.absdiff(gray, cv2.medianBlur(gray, int(max_px * 2) | 1))


def _speck_limit(contrast: np.ndarray) -> float:
    return max(_DUST_MIN_CONTRAST, 3 * _robust_p99(contrast))


def _match(seen: np.ndarray, want: np.ndarray) -> bool:
    """Same speck pattern? (correlation of contrast over the speck's box)"""
    if seen.std() == 0 or want.std() == 0:
        return False
    return float(np.corrcoef(seen.ravel(), want.ravel())[0, 1]) >= _DUST_MIN_MATCH


def _find_dust(contrast: np.ndarray, dpi: int) -> tuple[np.ndarray, int]:
    """Small specks that stand out from their immediate surroundings on the empty glass."""
    max_px = _DUST_MAX_MM / 25.4 * dpi
    specks = (contrast > _speck_limit(contrast)).astype(np.uint8)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(specks, connectivity=8)
    longest = stats[1:, [cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT]].max(axis=1, initial=0)
    keep = np.flatnonzero(longest <= max_px) + 1
    dust = np.isin(labels, keep).astype(np.uint8)
    # Grow each speck a little so its soft edge is repaired too.
    grow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * (1 + dpi // 300) + 1,) * 2)
    return cv2.dilate(dust, grow).astype(bool), len(keep)


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
