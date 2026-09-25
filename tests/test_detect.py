import numpy as np
import pytest

from photoscan.detect import Region, calibrate, cut, find_prints, match_backs, repair_dust
from tests.synthetic import DARK, WHITE, FakePrint, make_scan

DPI = 150


def _is_background(pixels: np.ndarray, background) -> np.ndarray:
    return np.abs(pixels.astype(int) - np.array(background)).max(axis=-1) < 12


def _extracts(scan, **kwargs):
    return [cut(scan, r) for r in find_prints(scan, DPI, **kwargs)]


def test_empty_scan_has_no_prints():
    assert find_prints(make_scan([]), DPI) == []


def test_finds_each_print_in_reading_order():
    prints = [
        FakePrint((850, 300), (450, 300)),
        FakePrint((300, 300), (300, 450)),
        FakePrint((600, 1200), (600, 400)),
    ]
    regions = find_prints(make_scan(prints), DPI)

    assert len(regions) == 3
    centers = [c for r in regions for c in r.center]
    assert centers == pytest.approx([300, 300, 850, 300, 600, 1200], abs=5)


@pytest.mark.parametrize("angle", [-8.0, -2.5, 3.0, 9.0])
def test_tilted_print_comes_out_straight_with_no_background(angle):
    scan = make_scan([FakePrint((600, 700), (600, 400), angle=angle)])

    (extract,) = _extracts(scan)

    height, width = extract.shape[:2]
    assert width == pytest.approx(600, abs=10)
    assert height == pytest.approx(400, abs=10)
    ring = np.concatenate(
        [
            extract[:2].reshape(-1, 3),
            extract[-2:].reshape(-1, 3),
            extract[:, :2].reshape(-1, 3),
            extract[:, -2:].reshape(-1, 3),
        ]
    )
    assert _is_background(ring, DARK).mean() < 0.01


def test_portrait_print_stays_portrait():
    (extract,) = _extracts(make_scan([FakePrint((600, 700), (400, 600), angle=4)]))
    assert extract.shape[0] > extract.shape[1]


def test_dust_and_specks_are_ignored():
    scan = make_scan([FakePrint((600, 700), (450, 300))], dust=40)
    assert len(find_prints(scan, DPI)) == 1


def test_small_id_photo_is_kept_but_below_min_size_is_not():
    # 2.5 cm at 150 dpi is ~148 px.
    scan = make_scan([FakePrint((300, 300), (200, 260)), FakePrint((900, 900), (120, 120))])
    regions = find_prints(scan, DPI, min_side_cm=2.5)
    assert len(regions) == 1
    assert min(regions[0].size) == pytest.approx(200, abs=6)


def test_white_bordered_print_on_dark_background():
    scan = make_scan([FakePrint((600, 700), (600, 400), angle=2, border=True)])
    (extract,) = _extracts(scan)
    assert extract.shape[1] == pytest.approx(600, abs=10)


def test_colour_prints_on_white_lid():
    prints = [FakePrint((350, 400), (450, 300), angle=-3), FakePrint((800, 1200), (450, 600))]
    assert len(find_prints(make_scan(prints, background=WHITE), DPI)) == 2


def test_print_pushed_into_the_corner_of_the_glass():
    scan = make_scan([FakePrint((225, 150), (450, 300)), FakePrint((800, 1200), (450, 300))])
    regions = find_prints(scan, DPI)
    assert len(regions) == 2
    assert cut(scan, regions[0]).shape[1] == pytest.approx(450, abs=10)


def test_16_bit_scan_gives_16_bit_extracts():
    scan8 = make_scan([FakePrint((600, 700), (450, 300))])
    scan16 = scan8.astype(np.uint16) * 257

    (extract,) = [cut(scan16, r) for r in find_prints(scan16, DPI)]

    assert extract.dtype == np.uint16
    assert extract.shape[1] == pytest.approx(450, abs=10)


def test_polaroids_on_the_white_lid_keep_their_frame():
    # Real case (2026-09-24): bluish-white frames only ~12 Lab units from the
    # lid; the high-contrast picture inside must not raise the threshold above them.
    frame = (226, 231, 240)
    scan = make_scan(
        [FakePrint((300, 500), (450, 540), frame=frame),
         FakePrint((900, 500), (450, 540), angle=2, frame=frame)],
        background=WHITE,
    )  # fmt: skip

    extracts = _extracts(scan)

    assert len(extracts) == 2
    for extract in extracts:
        assert extract.shape[1] == pytest.approx(450, abs=10)
        assert extract.shape[0] == pytest.approx(540, abs=10)


GLASS_DUST = [(200, 150), (640, 700), (700, 760), (1000, 1500)]


def test_calibration_measures_the_background_and_finds_glass_dust():
    empty = make_scan([], background=WHITE, glass_dust=GLASS_DUST)

    calibration = calibrate(empty, DPI)

    assert calibration.dust_specks == len(GLASS_DUST)
    for x, y in GLASS_DUST:
        assert calibration.dust[y, x]
    assert calibration.noise < 5


def test_calibrated_detection_ignores_vignetting_at_the_glass_edge():
    # The Print touches the darkened edge: uncalibrated, the vignette would
    # stretch its box; the calibration's reference cancels it out.
    prints = [FakePrint((233, 700), (450, 300))]
    empty = make_scan([], background=WHITE, vignette=20, seed=1)
    scan = make_scan(prints, background=WHITE, vignette=20, seed=2)

    (region,) = find_prints(scan, DPI, calibration=calibrate(empty, DPI))

    assert region.size[0] == pytest.approx(450, abs=6)
    assert region.size[1] == pytest.approx(300, abs=6)


def test_glass_dust_is_repaired_in_the_extract():
    prints = [FakePrint((600, 700), (600, 400))]
    calibration = calibrate(make_scan([], glass_dust=GLASS_DUST, seed=1), DPI)
    clean = make_scan(prints, seed=2)
    dusty = make_scan(prints, glass_dust=GLASS_DUST, seed=2)
    (region,) = find_prints(dusty, DPI, calibration=calibration)

    repaired, spots = repair_dust(cut(dusty, region), calibration, region)

    assert spots == 2  # the two specks that lie on the Print
    reference = cut(clean, region).astype(int)
    before = np.abs(cut(dusty, region).astype(int) - reference).max()
    after = np.abs(repaired.astype(int) - reference).max()
    assert before > 60
    assert after < before / 2


def test_lint_on_the_lid_hidden_behind_a_print_is_not_repaired():
    # The empty-glass Scan can't tell glass dust from lint on the lid's pad.
    # Glass dust shows on the Print; lid lint ends up behind it, so the Extract
    # must be left alone there.
    glass, lid = (640, 700), (800, 600)
    calibration = calibrate(make_scan([], glass_dust=[glass, lid], seed=1), DPI)
    prints = [FakePrint((600, 700), (600, 400))]
    scan = make_scan(prints, glass_dust=[glass], seed=2)
    (region,) = find_prints(scan, DPI, calibration=calibration)

    repaired, spots = repair_dust(cut(scan, region), calibration, region)

    assert spots == 1
    x, y = lid[0] - 300 - 2, lid[1] - 500 - 2  # into Extract coordinates (inset 2)
    np.testing.assert_array_equal(
        repaired[y - 5 : y + 5, x - 5 : x + 5], cut(scan, region)[y - 5 : y + 5, x - 5 : x + 5]
    )


def test_dense_lint_is_all_found_and_does_not_inflate_the_threshold():
    # Real lid (2026-09-24): ~1900 fibres. Noise estimates must stay robust to
    # them: frames ~12 units away must still pass, and every speck be found.
    lint = [(x, y) for x in range(20, 1260, 25) for y in range(20, 1740, 25)]
    calibration = calibrate(make_scan([], background=WHITE, glass_dust=lint), DPI)
    assert calibration.threshold == 8
    assert calibration.dust_specks == len(lint)


def _region(cx, cy, w, h, angle=0.0):
    from photoscan.detect import Region

    return Region(center=(cx, cy), size=(w, h), angle=angle)


def test_backs_match_their_fronts_despite_moving_and_turning_a_little():
    fronts = [
        _region(300, 300, 450, 300),
        _region(900, 300, 450, 300),
        _region(600, 1200, 300, 450),
    ]
    # Flipped in place: each moved up to ~1.5 cm (at 150 dpi, 1 cm = 59 px) and
    # turned a few degrees; one was flipped the other way round (sides swapped).
    backs = [
        _region(640, 1170, 450, 300, 4),
        _region(260, 330, 450, 300, -3),
        _region(930, 280, 300, 450),
    ]

    pairs, unmatched = match_backs(fronts, backs, DPI)

    assert pairs == {0: 1, 1: 2, 2: 0}
    assert unmatched == []


def test_a_back_too_far_from_any_front_is_unmatched_not_guessed():
    fronts = [_region(300, 300, 450, 300)]
    backs = [_region(300, 1200, 450, 300)]  # moved ~15 cm

    assert match_backs(fronts, backs, DPI) == ({}, [0])


def test_swapped_prints_of_different_sizes_are_told_apart_by_size():
    fronts = [_region(300, 300, 450, 300), _region(700, 300, 300, 200)]
    backs = [_region(700, 300, 450, 300), _region(300, 300, 300, 200)]  # swapped places

    pairs, unmatched = match_backs(fronts, backs, DPI, tolerance_cm=8)

    assert pairs == {0: 0, 1: 1}
    assert unmatched == []


def test_shade_between_prints_does_not_join_them_when_calibrated():
    # Real case (2026-09-24): two Prints 2.5 mm apart on the white lid, one a thick
    # Polaroid. The lid sat differently than during calibration and shaded the gap
    # ~7 units off the empty-glass reference, joining both Prints into one Extract.
    # Measured there: the gap was 7.1 from the reference but only 3.3 from the
    # Scan's own lid colour. The lid sat a little differently with Prints on the
    # glass, so the whole lid is shaded slightly darker than at calibration.
    empty = make_scan([], background=WHITE, seed=1)
    prints = [FakePrint((300, 500), (450, 600)), FakePrint((780, 400), (450, 400))]
    shaded_lid = tuple(c - 10 for c in WHITE)
    scan = make_scan(prints, background=shaded_lid, seed=2)

    regions = find_prints(scan, DPI, calibration=calibrate(empty, DPI))

    assert len(regions) == 2
    assert [round(r.size[0]) for r in regions] == pytest.approx([450, 450], abs=8)


@pytest.mark.parametrize("angle", [0.0, -2.0])
@pytest.mark.parametrize("calibrated", [False, True])
def test_a_printed_caption_strip_stays_with_its_print(angle, calibrated):
    # Real case (2026-09-24): "20KM DE LAUSANNE 2009" printed on a white strip
    # under the photo, on the white lid. The strip's paper is only 2-5 units off
    # the lid, so only its text was detected, as fragments, and the strip was cut off.
    empty = make_scan([], background=WHITE, seed=1)
    prints = [FakePrint((600, 800), (700, 840), angle=angle, caption=True)]
    scan = make_scan(prints, background=WHITE, seed=2)
    calibration = calibrate(empty, DPI) if calibrated else None

    (region,) = find_prints(scan, DPI, calibration=calibration)

    assert region.size[0] == pytest.approx(700, abs=10)
    assert region.size[1] == pytest.approx(840, abs=10)  # caption included, no lid added


def test_no_caption_no_extension_even_next_to_another_print():
    # 50 px (~8 mm) of plain lid between the two: no text, so neither is extended.
    prints = [FakePrint((330, 500), (450, 600)), FakePrint((830, 500), (450, 600))]
    regions = find_prints(make_scan(prints, background=WHITE), DPI)
    assert [round(r.size[0]) for r in regions] == pytest.approx([450, 450], abs=6)


def test_a_caption_between_two_prints_belongs_to_the_nearest_only():
    # Real case (2026-09-24): the caption strip of a race photo lay between it
    # and the Print below. Both claimed the text, and the upper one's edge
    # search ran into the lower Print's edge: the two Extracts overlapped.
    prints = [
        FakePrint((400, 480), (700, 840), caption=True),  # caption ends at y=900
        FakePrint((400, 1155), (600, 400)),  # top edge 55 px (~0.9 cm) below, as measured
    ]
    regions = find_prints(make_scan(prints, background=WHITE), DPI)

    upper, lower = regions
    assert upper.size[1] == pytest.approx(840, abs=10)  # caption included, no more
    assert lower.size[1] == pytest.approx(400, abs=8)  # not extended over the caption
    assert upper.center[1] + upper.size[1] / 2 < lower.center[1] - lower.size[1] / 2


@pytest.mark.parametrize("calibrated", [False, True])
def test_prints_joined_by_a_shadow_in_a_narrow_gap_are_split(calibrated):
    # Real case (2026-09-24): a photo and a thick Polaroid 2.5 mm apart on the
    # white lid; along part of the gap a shadow read as "not lid", bridging them
    # into one shape that came out as a single Extract.
    left, right = FakePrint((300, 500), (500, 700)), FakePrint((690, 560), (250, 500))
    empty = make_scan([], background=WHITE, seed=1)
    scan = make_scan([left, right], background=WHITE, seed=2)
    scan[330:520, 550:566] = (200, 200, 200)  # the shadow in the 15 px gap (x 550-565)
    calibration = calibrate(empty, DPI) if calibrated else None

    regions = find_prints(scan, DPI, calibration=calibration)

    assert len(regions) == 2
    assert [tuple(round(s) for s in r.size) for r in regions] == [
        pytest.approx((500, 700), abs=8),
        pytest.approx((250, 500), abs=8),
    ]


def test_prints_covering_the_glass_edges_do_not_fool_the_lid_colour():
    # Real case (2026-09-25): four Prints filling the glass, touching nearly every
    # edge. Only 6% of the Scan's edge was still lid, so the "lid colour" taken
    # from the edge came out as a photo's near-black: every dark area inside the
    # photos then read as lid, and the four Prints were cut into 8 pieces.
    dark = (25, 25, 28)
    prints = [
        FakePrint((300, 430), (600, 860), frame=dark),
        FakePrint((958, 430), (634, 860), frame=dark),
        FakePrint((300, 1327), (600, 854), frame=dark),
        FakePrint((958, 1327), (634, 854), frame=dark),
    ]  # 40 px (~7 mm) gaps, flush with every edge of the glass
    empty = make_scan([], background=WHITE, seed=1)
    scan = make_scan(prints, background=WHITE, seed=2)

    regions = find_prints(scan, DPI, calibration=calibrate(empty, DPI))

    assert len(regions) == 4
    assert [tuple(round(s) for s in r.size) for r in regions] == [
        pytest.approx((600, 860), abs=10),
        pytest.approx((634, 860), abs=10),
        pytest.approx((600, 854), abs=10),
        pytest.approx((634, 854), abs=10),
    ]


def test_same_picture_tells_an_unflipped_print_from_its_back():
    from photoscan.detect import same_picture

    front = cut(make_scan([FakePrint((600, 700), (600, 400))]), Region((600, 700), (600, 400), 0))
    moved = front[3:-3, 3:-3].astype(int)  # a few px off, with scanner noise
    rescanned = moved + np.random.default_rng(1).normal(0, 3, moved.shape)
    back = np.full_like(front, 238)
    back[180:220, 100:500] = 60  # a lab stamp

    assert same_picture(front, np.clip(rescanned, 0, 255).astype(np.uint8))
    assert not same_picture(front, back)
