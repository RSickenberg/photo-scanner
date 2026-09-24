import json
from datetime import date, datetime

import numpy as np
import pytest
import tifffile
from PIL import Image

from photoscan.imagefiles import read_label
from photoscan.session import Session, rotate_extract
from tests.synthetic import FakePrint, make_scan

DAY = date(2026, 9, 24)
DPI = 150


@pytest.fixture
def two_print_scan():
    return make_scan([FakePrint((300, 300), (450, 300)), FakePrint((600, 1200), (300, 450))])


def test_session_folder_is_named_from_date_and_label(tmp_path):
    session = Session.open(tmp_path, "Grand-mère album 1970s", DAY)

    assert session.path == tmp_path / "2026-09-24_grand-mere-album-1970s"
    assert json.loads((session.path / "session.json").read_text())["label"] == (
        "Grand-mère album 1970s"
    )


def test_a_scan_is_kept_whole_and_cut_into_one_extract_per_print(tmp_path, two_print_scan):
    session = Session.open(tmp_path, "Grandma", DAY)

    extracts = session.add_scan(two_print_scan, DPI).extracts

    assert (session.path / "scans" / "grandma_s001.tif").exists()
    assert [p.name for p in extracts] == ["grandma_s001_p01.tif", "grandma_s001_p02.tif"]
    for tif in extracts:
        assert tif.with_suffix(".jpg").exists()


def test_scans_are_numbered_in_sequence(tmp_path, two_print_scan):
    session = Session.open(tmp_path, "Grandma", DAY)
    session.add_scan(two_print_scan, DPI)
    session.add_scan(two_print_scan, DPI)

    assert sorted(p.name for p in (session.path / "scans").iterdir()) == [
        "grandma_s001.tif",
        "grandma_s002.tif",
    ]


def test_reopening_a_session_continues_numbering(tmp_path, two_print_scan):
    Session.open(tmp_path, "Grandma", DAY).add_scan(two_print_scan, DPI)

    extracts = Session.open(tmp_path, "Grandma", DAY).add_scan(two_print_scan, DPI).extracts

    assert extracts[0].name == "grandma_s002_p01.tif"


def test_numbering_continues_past_scans_already_pruned_locally(tmp_path, two_print_scan):
    session = Session.open(tmp_path, "Grandma", DAY)
    session.add_scan(two_print_scan, DPI)
    for f in session.path.glob("*/*"):
        f.unlink()

    reopened = Session.open(tmp_path, "Grandma", DAY, known=["grandma_s001.tif"])
    extracts = reopened.add_scan(two_print_scan, DPI).extracts

    assert extracts[0].name == "grandma_s002_p01.tif"


def test_extracts_carry_label_date_and_resolution(tmp_path, two_print_scan):
    session = Session.open(tmp_path, "Grand-mère 1970s", DAY)
    tif = session.add_scan(two_print_scan, DPI).extracts[0]
    jpg = tif.with_suffix(".jpg")

    assert read_label(tif) == "Grand-mère 1970s"
    assert read_label(jpg) == "Grand-mère 1970s"
    assert Image.open(jpg).info["dpi"] == pytest.approx((DPI, DPI))
    with tifffile.TiffFile(tif) as t:
        page = t.pages[0]
        assert page.compression != 1  # lossless compressed, not raw
        assert page.tags["DateTime"].value.startswith("2026:09:24")


def test_16_bit_scan_gives_16_bit_tiff_and_8_bit_jpeg(tmp_path, two_print_scan):
    session = Session.open(tmp_path, "Grandma", DAY)
    tif = session.add_scan(two_print_scan.astype(np.uint16) * 257, DPI).extracts[0]

    assert tifffile.imread(tif).dtype == np.uint16
    assert Image.open(tif.with_suffix(".jpg")).mode == "RGB"


def test_recut_replaces_the_extracts_of_that_scan(tmp_path, two_print_scan):
    session = Session.open(tmp_path, "Grandma", DAY)
    session.add_scan(two_print_scan, DPI)
    one_print = make_scan([FakePrint((600, 700), (450, 300))])
    scan_path = session.path / "scans" / "grandma_s001.tif"
    tifffile.imwrite(scan_path, one_print, photometric="rgb", resolution=(DPI, DPI))

    extracts = session.recut(scan_path)

    assert [p.name for p in extracts] == ["grandma_s001_p01.tif"]
    assert not (session.path / "extracts" / "grandma_s001_p02.tif").exists()
    assert not (session.path / "extracts" / "grandma_s001_p02.jpg").exists()


def test_rotate_turns_both_tiff_and_jpeg_and_keeps_label(tmp_path, two_print_scan):
    session = Session.open(tmp_path, "Grandma", DAY)
    tif = session.add_scan(two_print_scan, DPI).extracts[0]
    height, width = tifffile.imread(tif).shape[:2]

    rotate_extract(tif.with_suffix(".jpg"), 90)

    assert tifffile.imread(tif).shape[:2] == (width, height)
    assert Image.open(tif.with_suffix(".jpg")).size == (height, width)
    assert read_label(tif) == "Grandma"


def test_discarding_the_last_scan_frees_its_number(tmp_path, two_print_scan):
    session = Session.open(tmp_path, "Grandma", DAY)
    first = session.add_scan(two_print_scan, DPI)

    session.discard(first.scan)
    again = session.add_scan(two_print_scan, DPI)

    assert again.scan == first.scan
    assert len(list((session.path / "extracts").iterdir())) == 4


def test_load_reopens_a_session_from_its_folder(tmp_path, two_print_scan):
    path = Session.open(tmp_path, "Grand-mère", DAY).path

    session = Session.load(path)

    assert (session.label, session.day, session.path) == ("Grand-mère", DAY, path)


def _record(session):
    return json.loads((session.path / "session.json").read_text())


def test_session_json_records_each_scan_with_its_extracts(tmp_path, two_print_scan):
    session = Session.open(tmp_path, "Grandma", DAY)

    session.add_scan(two_print_scan, DPI, scanner="pixma:04A91912")

    record = _record(session)
    (scan,) = record["scans"]
    assert scan["scan"] == "grandma_s001"
    assert scan["extracts"] == ["grandma_s001_p01", "grandma_s001_p02"]
    assert scan["scanner"] == "pixma:04A91912"
    assert (scan["dpi"], scan["bits"]) == (DPI, 8)
    assert datetime.fromisoformat(scan["scanned_at"])
    assert record["totals"] == {"scans": 1, "extracts": 2}


def test_record_survives_reopening_the_session(tmp_path, two_print_scan):
    Session.open(tmp_path, "Grandma", DAY).add_scan(two_print_scan, DPI)

    session = Session.open(tmp_path, "Grandma", DAY)
    session.add_scan(two_print_scan, DPI)

    assert [s["scan"] for s in _record(session)["scans"]] == ["grandma_s001", "grandma_s002"]
    assert _record(session)["totals"] == {"scans": 2, "extracts": 4}


def test_record_follows_discard_and_recut(tmp_path, two_print_scan):
    session = Session.open(tmp_path, "Grandma", DAY)
    first = session.add_scan(two_print_scan, DPI)
    discarded = session.add_scan(two_print_scan, DPI)
    session.discard(discarded.scan)
    tifffile.imwrite(
        first.scan,
        make_scan([FakePrint((600, 700), (450, 300))]),
        photometric="rgb",
        resolution=(DPI, DPI),
    )

    session.recut(first.scan)

    (scan,) = _record(session)["scans"]
    assert scan["extracts"] == ["grandma_s001_p01"]
    assert datetime.fromisoformat(scan["recut_at"])
    assert _record(session)["totals"] == {"scans": 1, "extracts": 1}


def test_session_from_before_records_existed_still_opens(tmp_path, two_print_scan):
    path = Session.folder(tmp_path, "Grandma", DAY)
    path.mkdir()
    (path / "session.json").write_text('{"label": "Grandma", "date": "2026-09-24"}')

    Session.load(path).add_scan(two_print_scan, DPI)

    assert json.loads((path / "session.json").read_text())["totals"]["scans"] == 1


GLASS_DUST = [(640, 1100), (1100, 150)]


def _calibrated(tmp_path):
    session = Session.open(tmp_path, "Grandma", DAY)
    session.calibrate(make_scan([], glass_dust=GLASS_DUST, seed=5), DPI, scanner="pixma:x")
    return session


def test_calibration_is_saved_and_recorded(tmp_path):
    session = _calibrated(tmp_path)

    (cal,) = _record(session)["calibrations"]
    assert (session.path / "calibration" / "cal_01.tif").exists()
    assert cal["id"] == "cal_01"
    assert cal["scanner"] == "pixma:x"
    assert cal["dpi"] == DPI
    assert cal["dust_specks"] == 2
    assert cal["threshold"] >= 8
    assert len(cal["background_lab"]) == 3
    assert datetime.fromisoformat(cal["calibrated_at"])


def test_scans_record_their_calibration_and_dust_repairs(tmp_path):
    session = _calibrated(tmp_path)
    scan = make_scan(
        [FakePrint((300, 300), (450, 300)), FakePrint((600, 1200), (300, 450))],
        glass_dust=GLASS_DUST,
    )

    session.add_scan(scan, DPI)

    (entry,) = _record(session)["scans"]
    assert entry["calibration"] == "cal_01"
    # (640, 1100) lies on the second Print; (1100, 150) on neither.
    assert entry["dust_repaired"] == {"grandma_s001_p01": 0, "grandma_s001_p02": 1}


def test_recalibrating_mid_session_numbers_the_next_calibration(tmp_path):
    session = _calibrated(tmp_path)
    session.calibrate(make_scan([]), DPI)

    assert [c["id"] for c in _record(session)["calibrations"]] == ["cal_01", "cal_02"]


def test_recut_reuses_the_scans_own_calibration(tmp_path):
    session = _calibrated(tmp_path)
    scan = make_scan([FakePrint((600, 1200), (300, 450))], glass_dust=GLASS_DUST)
    result = session.add_scan(scan, DPI)
    session.calibrate(make_scan([]), DPI)  # a later calibration, without dust

    Session.load(session.path).recut(result.scan)

    (entry,) = _record(session)["scans"]
    assert entry["calibration"] == "cal_01"
    assert entry["dust_repaired"] == {"grandma_s001_p01": 1}


def test_uncalibrated_scans_say_so(tmp_path):
    session = Session.open(tmp_path, "Grandma", DAY)
    session.add_scan(make_scan([FakePrint((600, 700), (450, 300))]), DPI)

    assert _record(session)["scans"][0]["calibration"] is None
