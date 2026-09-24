"""Find the Prints on a Scan, cut each one out straightened, repair glass dust.

A Calibration, made from a Scan of the empty glass, makes this more precise:
Prints are found against that exact background (vignetting, lid streaks and
all) instead of a single colour guessed from the Scan's border, and specks of
dust on the glass are known and repaired in every Extract.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from photoscan.imagefiles import to_8bit

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
# Prints joined across a partly bridged gap are split where lines across the
# shape are at most this covered, relative to the best-covered line within
# _SPLIT_WINDOW_CM on either side. (Real gap: ~15% covered; Prints: ~100%.)
_SPLIT_MAX_COVERAGE = 0.5
_SPLIT_WINDOW_CM = 1.0
# Printed captions: text fragments this close to a Print's side (cm) extend
# that side over them, then up to the paper's edge if one is found just beyond.
_CAPTION_REACH_CM = 2.5
_CAPTION_EDGE_SEARCH_CM = 1.5
_CAPTION_EDGE_MIN_STEP = 2.0  # Lab L units: paper vs lid, or the edge's highlight
# How far a Print may move when flipped for its Back to still be paired.
BACK_TOLERANCE_CM = 3.0


@dataclass(frozen=True)
class Region:
    """Where one Print sits on a Scan, in full-resolution pixels."""

    center: tuple[float, float]  # (x, y)
    size: tuple[float, float]  # (width, height), as the Print is oriented on the glass
    angle: float  # degrees, as returned by cv2.minAreaRect, normalised to [-45, 45)

    @classmethod
    def around(cls, points: np.ndarray) -> "Region":
        """The smallest box around these points (a contour, or corners), straightened.

        minAreaRect may report a 3° tilt as (h, w, 93°) or (w, h, -87°): the
        angle is folded into [-45, 45) and the sides swapped accordingly, so a
        landscape Print stays landscape.
        """
        (cx, cy), (w, h), angle = cv2.minAreaRect(points)
        while angle >= 45:
            angle -= 90
            w, h = h, w
        while angle < -45:
            angle += 90
            w, h = h, w
        return cls(center=(cx, cy), size=(w, h), angle=angle)

    @classmethod
    def from_list(cls, values: list[float]) -> "Region":
        cx, cy, w, h, angle = values
        return cls(center=(cx, cy), size=(w, h), angle=angle)

    def as_list(self) -> list[float]:
        """[cx, cy, width, height, angle], as kept in the Source's record."""
        return [round(v, 2) for v in (*self.center, *self.size, self.angle)]

    def box(self) -> np.ndarray:
        """The four corners (float32), in the same pixels as the Region."""
        return cv2.boxPoints((self.center, self.size, self.angle)).astype(np.float32)

    def scaled(self, factor: float) -> "Region":
        """The same Region in pixels `factor` times bigger (e.g. another dpi)."""
        (cx, cy), (w, h) = self.center, self.size
        return Region((cx * factor, cy * factor), (w * factor, h * factor), self.angle)


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
    empty8 = to_8bit(empty)
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
    small, scale = _downscale(to_8bit(scan))
    raw = _raw_mask(small, calibration)
    mask = _clean(raw)

    min_side_px = min_side_cm / 2.54 * dpi * scale
    px_per_cm = dpi * scale / 2.54
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions, bodies, fragments = [], [], []
    for contour in contours:
        if min(cv2.minAreaRect(contour)[1]) < min_side_px:
            fragments.append(contour)
            continue
        for body in _split_at_gaps(contour, mask, raw, min_side_px, px_per_cm):
            regions.append(Region.around(body))
            bodies.append(body)

    # Each fragment (e.g. caption text) belongs to the nearest Print only.
    owned = [np.zeros_like(mask) for _ in regions]
    for fragment in fragments:
        (fx, fy), _, _ = cv2.minAreaRect(fragment)
        if regions:
            nearest = min(range(len(regions)), key=lambda i: distance_outside(regions[i], (fx, fy)))
            cv2.drawContours(owned[nearest], [fragment], -1, 255, cv2.FILLED)
    lightness = _lab(small)[..., 0]
    grown = []
    for i, region in enumerate(regions):
        others = np.zeros_like(mask)
        cv2.drawContours(others, [b for j, b in enumerate(bodies) if j != i], -1, 255, cv2.FILLED)
        grown.append(_attach_caption(region, owned[i], others, lightness, px_per_cm))
    return _reading_order([r.scaled(1 / scale) for r in grown])


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
    found = _speck_contrast(cv2.cvtColor(to_8bit(extract), cv2.COLOR_RGB2GRAY), calibration.dpi)
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
    fronts: list[Region], backs: list[Region], dpi: int, *, tolerance_cm: float = BACK_TOLERANCE_CM
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


def distance_outside(region: Region, point: tuple[float, float]) -> float:
    """How far `point` lies outside `region` (0 when inside), in pixels."""
    inside = cv2.pointPolygonTest(region.box(), (float(point[0]), float(point[1])), True)
    return max(0.0, -inside)


def enclose(regions: list[Region]) -> Region:
    """The smallest (rotated) box around all these regions."""
    return Region.around(np.concatenate([r.box() for r in regions]))


def _upright(image: np.ndarray, region: Region, inset_px: int, interpolation: int) -> np.ndarray:
    (w, h) = region.size
    # Rotated, and shifted so the Print lands centred in an output of exactly its own size.
    upright = cv2.warpAffine(
        image,
        _upright_matrix(region),
        (round(w), round(h)),
        flags=interpolation,
        borderMode=cv2.BORDER_REPLICATE,
    )
    if inset_px:
        upright = upright[inset_px:-inset_px, inset_px:-inset_px]
    return upright


def _split_at_gaps(
    contour: np.ndarray,
    mask: np.ndarray,
    raw: np.ndarray,
    min_side_px: float,
    px_per_cm: float,
    depth: int = 0,
) -> list[np.ndarray]:
    """Split a shape made of several Prints whose narrow gap was partly bridged.

    Two Prints 2-3 mm apart can be joined by a shadow along part of the gap (a
    thick Polaroid next to a photo, on a real Scan). The bridge is short but
    wide, so shrinking the shape doesn't cut it; but the gap stays a straight
    line across the shape that's mostly lid. Inside a Print, lines across are
    covered all along. So: a narrow valley in line coverage, between two
    Print-sized parts, is a gap; cut there, and try again on each part.
    Coverage is measured on the raw mask: the clean-up that fills small holes
    inside Prints would also fill a 2-3 mm gap.
    """
    region = Region.around(contour)
    shape = np.zeros_like(mask)
    cv2.drawContours(shape, [contour], -1, 255, cv2.FILLED)
    upright_shape = _upright(shape & mask, region, 0, cv2.INTER_NEAREST) > 0
    upright = _upright(shape & raw, region, 0, cv2.INTER_NEAREST) > 0
    matrix = _upright_matrix(region)
    window = max(3, round(_SPLIT_WINDOW_CM * px_per_cm))
    for axis in (0, 1):  # a cut along columns, then along rows
        coverage = upright.mean(axis=axis)
        gap = _gap_in(coverage, round(min_side_px), window)
        if gap is None:
            continue
        cut, resume = gap
        # The parts keep the cleaned shape: only the cut line comes from the raw mask.
        whole = upright_shape
        # The gap itself (bridge included) goes to neither part.
        halves = (whole[:, :cut], whole[:, resume:]) if axis == 0 else (whole[:cut], whole[resume:])
        offsets = ((0, 0), (resume, 0)) if axis == 0 else ((0, 0), (0, resume))
        parts = []
        for half, (dx, dy) in zip(halves, offsets, strict=True):
            placed = np.zeros_like(whole, dtype=np.uint8)
            placed[dy : dy + half.shape[0], dx : dx + half.shape[1]] = half * 255
            back = cv2.warpAffine(
                placed, cv2.invertAffineTransform(matrix), mask.shape[1::-1],
                flags=cv2.INTER_NEAREST,
            )  # fmt: skip
            outlines, _ = cv2.findContours(back, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not outlines:
                return [contour]
            part = max(outlines, key=cv2.contourArea)
            if depth < 3:
                parts += _split_at_gaps(part, back, raw, min_side_px, px_per_cm, depth + 1)
            else:
                parts.append(part)
        return parts
    return [contour]


def _gap_in(coverage: np.ndarray, min_part: int, window: int) -> tuple[int, int] | None:
    """The deepest narrow dip in coverage leaving at least `min_part` on each side,
    as the span [start, end) of lines that belong to the gap."""
    best, where, limit = 1.0, None, 0.0
    for i in range(min_part, len(coverage) - min_part):
        around = min(coverage[max(0, i - window) : i].max(), coverage[i + 1 : i + 1 + window].max())
        if coverage[i] < _SPLIT_MAX_COVERAGE * around and coverage[i] < best:
            best, where, limit = coverage[i], i, _SPLIT_MAX_COVERAGE * around
    if where is None:
        return None
    start, end = where, where + 1
    while start > 0 and coverage[start - 1] < limit:
        start -= 1
    while end < len(coverage) and coverage[end] < limit:
        end += 1
    return start, end


def _upright_matrix(region: Region) -> np.ndarray:
    (cx, cy), (w, h) = region.center, region.size
    matrix = cv2.getRotationMatrix2D((cx, cy), region.angle, 1.0)
    matrix[0, 2] += w / 2 - cx
    matrix[1, 2] += h / 2 - cy
    return matrix


def _attach_caption(
    region: Region,
    fragments: np.ndarray,
    others: np.ndarray,
    lightness: np.ndarray,
    px_per_cm: float,
) -> Region:
    """Extend a Print over a printed caption on its own pale margin.

    A white strip with printed text ("20KM DE LAUSANNE 2009") is barely off a
    white lid (2-5 units on a real Scan): only its text is detected, as small
    fragments next to the photo. A side with such fragments within reach is
    extended over them, then up to the paper's edge (a highlight or a step in
    lightness running along the side) if one is found just beyond. Without
    text nearby, nothing is extended: streaks in the lid are straight too.
    (Works in detection pixels.)
    """
    reach = round(_CAPTION_REACH_CM * px_per_cm)
    search = round(_CAPTION_EDGE_SEARCH_CM * px_per_cm)
    pad = reach + search
    w, h = round(region.size[0]), round(region.size[1])
    grown = Region(region.center, (w + 2 * pad, h + 2 * pad), region.angle)
    near = _upright(fragments, grown, 0, cv2.INTER_NEAREST)
    blocked = _upright(others, grown, 0, cv2.INTER_NEAREST)
    light = _upright(lightness, grown, 0, cv2.INTER_LINEAR)

    # The Print occupies [pad, pad + h) x [pad, pad + w) in these upright views.
    # Each side is turned to the bottom (np.rot90 turns counter-clockwise: the
    # left side comes to the bottom after one turn), then read outward from it.
    grow = {}
    for side, turns in (("bottom", 0), ("left", 1), ("top", 2), ("right", 3)):
        text, other, profile = (np.rot90(v, turns) for v in (near, blocked, light))
        side_len, depth = (w, h) if turns % 2 == 0 else (h, w)
        along = slice(pad, pad + side_len)
        outward = slice(pad + depth, None)
        rows = np.flatnonzero(text[outward, along][:reach].any(axis=1))
        if not len(rows):
            continue
        text_end = int(rows[-1]) + 1
        # Never reach into another Print: its edge would be the strongest "step".
        hit = np.flatnonzero(other[outward, along].any(axis=1))
        limit = int(hit[0]) - 2 if len(hit) else profile.shape[0] - pad - depth
        if limit <= text_end:
            continue
        # Start past the text: its last strokes are a much stronger "step" than the edge.
        lightness_out = profile[outward, along][:limit].mean(axis=1)
        edge = _paper_edge(lightness_out, text_end + 4, min(search, limit - text_end - 4))
        grow[side] = edge or text_end + 1
    if not grow:
        return region

    # Grow the upright box, then map its new centre back onto the Scan.
    top, bottom = grow.get("top", 0), grow.get("bottom", 0)
    left, right = grow.get("left", 0), grow.get("right", 0)
    shift = np.array([(right - left) / 2, (bottom - top) / 2])
    rotation = cv2.getRotationMatrix2D((0, 0), -region.angle, 1.0)[:, :2]
    cx, cy = np.array(region.center) + rotation @ shift
    return Region((cx, cy), (w + left + right, h + top + bottom), region.angle)


def _paper_edge(profile: np.ndarray, start: int, search: int) -> int | None:
    """Where a pale margin ends, reading outward: the strongest highlight or
    step in lightness between `start` and `start + search`, if clear enough."""
    stop = min(len(profile) - 3, start + search)
    best, where = 0.0, None
    for d in range(max(start, 3), stop):
        step = abs(profile[d - 3 : d].mean() - profile[d : d + 3].mean())
        highlight = profile[d] - np.median(profile[max(0, d - 6) : d + 7])
        score = max(step, highlight)
        if score > best:
            best, where = score, d + 1
    return where if best >= _CAPTION_EDGE_MIN_STEP else None


def _downscale(img: np.ndarray) -> tuple[np.ndarray, float]:
    scale = min(1.0, _DETECT_LONG_SIDE / max(img.shape[:2]))
    if scale < 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img, scale


def _lab(img: np.ndarray) -> np.ndarray:
    # Median, not Gaussian: removes noise without smearing edges outwards, which a
    # low threshold would otherwise count as part of the Print.
    return cv2.cvtColor(cv2.medianBlur(img, 5), cv2.COLOR_RGB2LAB).astype(np.float32)


def _raw_mask(img: np.ndarray, calibration: Calibration | None) -> np.ndarray:
    """White where something differs from the glass/lid background, pixel by pixel."""
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
    return mask.astype(np.uint8) * 255


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
