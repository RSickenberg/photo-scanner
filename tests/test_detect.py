import numpy as np
import pytest

from photoscan.detect import cut, find_prints
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
