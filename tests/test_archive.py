import json
from datetime import date

import numpy as np
import pytest
import tifffile
from PIL import ExifTags, Image

from photoscan.archive import Archive
from photoscan.dates import PhotoDate
from photoscan.imagefiles import read_meta
from tests.synthetic import FakePrint, make_scan

DPI = 150
DAY = date(2026, 9, 24)
TWO_PRINTS = [FakePrint((300, 300), (450, 300)), FakePrint((600, 1200), (300, 450))]


class Reader:
    """Stands in for Apple Vision: returns whatever text the test sets."""

    def __init__(self):
        self.text: list[str] = []

    def __call__(self, image):
        return list(self.text)


@pytest.fixture
def reader():
    return Reader()


@pytest.fixture
def archive(tmp_path, reader):
    return Archive(tmp_path, reader=reader)


def _record(source):
    return json.loads((source.path / "source.json").read_text())


def _original_date(jpg):
    with Image.open(jpg) as img:
        return img.getexif().get_ifd(ExifTags.IFD.Exif).get(0x9003)


# --- Sources -----------------------------------------------------------------


def test_a_source_is_created_with_its_estimate_and_listed(archive):
    archive.source("Album Grand-mère", estimate=PhotoDate(1970, decade=True))

    (source,) = archive.sources()
    assert (source.name, source.slug, source.estimate) == (
        "Album Grand-mère",
        "album-grand-mere",
        PhotoDate(1970, decade=True),
    )
    assert _record(source)["estimate"] == "1970s"


def test_reopening_a_source_keeps_its_estimate(archive):
    archive.source("Album", estimate=PhotoDate(1985))
    assert archive.source("Album").estimate == PhotoDate(1985)


# --- Scans and Extracts --------------------------------------------------------


def test_scan_lands_in_the_archive_and_extracts_in_photos(archive, tmp_path):
    session = archive.start_session(DAY)
    source = archive.source("Album")

    result = session.add_scan(source, make_scan(TWO_PRINTS), DPI)

    assert result.scan == "album_s001"
    assert result.extracts == ["album_s001_p01", "album_s001_p02"]
    assert (tmp_path / "archive/album/scans/album_s001.tif").exists()
    for name in result.extracts:
        assert (tmp_path / f"archive/album/masters/{name}.tif").exists()
        assert (tmp_path / f"photos/album/{name}.jpg").exists()
    # Only the fronts' JPEGs go to photos/: that's the tree Ugreen Photos indexes.
    assert sorted(p.name for p in (tmp_path / "photos").rglob("*")) == [
        "album",
        "album_s001_p01.jpg",
        "album_s001_p02.jpg",
    ]


def test_scans_are_numbered_per_source_across_sessions(archive):
    album, box = archive.source("Album"), archive.source("Box")
    archive.start_session(DAY).add_scan(album, make_scan(TWO_PRINTS), DPI)

    session = archive.start_session(DAY)
    assert session.add_scan(album, make_scan(TWO_PRINTS), DPI).scan == "album_s002"
    assert session.add_scan(box, make_scan(TWO_PRINTS), DPI).scan == "box_s001"


def test_numbering_survives_local_files_being_pruned(archive, tmp_path):
    album = archive.source("Album")
    archive.start_session(DAY).add_scan(album, make_scan(TWO_PRINTS), DPI)
    for f in tmp_path.rglob("*"):
        if f.is_file() and f.suffix != ".json":
            f.unlink()

    assert archive.start_session(DAY).add_scan(album, make_scan(TWO_PRINTS), DPI).scan == (
        "album_s002"
    )


def test_discard_removes_the_scan_everywhere_and_frees_its_number(archive, tmp_path):
    session, album = archive.start_session(DAY), archive.source("Album")
    first = session.add_scan(album, make_scan(TWO_PRINTS), DPI)

    album.discard(first.scan)

    assert not [f for f in tmp_path.rglob("*.tif") if "_calibrations" not in f.parts]
    assert not list(tmp_path.rglob("*.jpg"))
    assert _record(album)["scans"] == []
    assert session.add_scan(album, make_scan(TWO_PRINTS), DPI).scan == "album_s001"


# --- Photo dates ---------------------------------------------------------------


def test_extracts_take_the_source_estimate_when_nothing_else_is_known(archive, tmp_path):
    album = archive.source("Album", estimate=PhotoDate(1970, decade=True))

    result = archive.start_session(DAY).add_scan(album, make_scan(TWO_PRINTS), DPI)

    jpg = tmp_path / f"photos/album/{result.extracts[0]}.jpg"
    assert _original_date(jpg) == "1970:01:01 12:00:00"
    assert read_meta(jpg).title == "Album"
    entry = _record(album)["scans"][0]["extracts"][0]
    assert (entry["date"], entry["date_source"]) == ("1970s", "source")


def test_unknown_date_stays_unknown(archive, tmp_path):
    result = archive.start_session(DAY).add_scan(archive.source("Box"), make_scan(TWO_PRINTS), DPI)

    assert _original_date(tmp_path / f"photos/box/{result.extracts[0]}.jpg") is None
    assert _record(archive.source("Box"))["totals"] == {
        "scans": 1,
        "extracts": 2,
        "dated": 0,
        "undated": 2,
    }


def test_a_typed_date_beats_everything(archive, reader, tmp_path):
    reader.text = ["18.05.98"]
    album = archive.source("Album", estimate=PhotoDate(1970, decade=True))

    result = archive.start_session(DAY).add_scan(
        album, make_scan(TWO_PRINTS), DPI, typed=PhotoDate(1984, 7)
    )

    assert _original_date(tmp_path / f"photos/album/{result.extracts[0]}.jpg") == (
        "1984:07:01 12:00:00"
    )


def test_a_date_printed_on_the_front_is_used_and_its_text_kept(archive, reader):
    reader.text = ["Je suis née 18.05.98 à"]
    album = archive.source("Album", estimate=PhotoDate(1990, decade=True))

    archive.start_session(DAY).add_scan(album, make_scan(TWO_PRINTS), DPI)

    entry = _record(album)["scans"][0]["extracts"][0]
    assert (entry["date"], entry["date_source"]) == ("1998-05-18", "ocr-front")
    assert entry["text_front"] == ["Je suis née 18.05.98 à"]


def test_setting_a_date_later_restamps_the_files(archive, tmp_path):
    album = archive.source("Album")
    result = archive.start_session(DAY).add_scan(album, make_scan(TWO_PRINTS), DPI)
    name = result.extracts[1]

    album.set_date(name, PhotoDate(1983, approximate=True))

    jpg = tmp_path / f"photos/album/{name}.jpg"
    assert _original_date(jpg) == "1983:01:01 12:00:00"
    assert read_meta(tmp_path / f"archive/album/masters/{name}.tif").photo_date == PhotoDate(
        1983, approximate=True
    )
    assert _original_date(tmp_path / f"photos/album/{result.extracts[0]}.jpg") is None


def test_changing_the_estimate_restamps_only_extracts_that_used_it(archive, reader):
    album = archive.source("Album", estimate=PhotoDate(1970, decade=True))
    session = archive.start_session(DAY)
    session.add_scan(album, make_scan(TWO_PRINTS), DPI)
    session.add_scan(album, make_scan(TWO_PRINTS), DPI, typed=PhotoDate(1966))

    album.set_estimate(PhotoDate(1975, approximate=True))

    dates = [e["date"] for s in _record(album)["scans"] for e in s["extracts"]]
    assert dates == ["ca. 1975", "ca. 1975", "1966", "1966"]


# --- Calibration and Sessions ----------------------------------------------------


def test_session_records_its_calibrations_and_scans(archive, tmp_path):
    session = archive.start_session(DAY)
    session.calibrate(make_scan([], glass_dust=[(1100, 150)]), DPI, scanner="pixma:x")
    session.add_scan(archive.source("Album"), make_scan(TWO_PRINTS), DPI)

    record = json.loads((tmp_path / "archive/_sessions/2026-09-24_01.json").read_text())
    (cal,) = record["calibrations"]
    assert cal["id"] == "2026-09-24_01_cal_01"
    assert cal["dust_specks"] == 1
    assert (tmp_path / "archive/_calibrations/2026-09-24_01_cal_01.tif").exists()
    assert record["scans"] == [{"source": "album", "scan": "album_s001"}]
    assert _record(archive.source("Album"))["scans"][0]["calibration"] == "2026-09-24_01_cal_01"


def test_second_session_of_the_day_gets_its_own_number(archive):
    archive.start_session(DAY)
    assert archive.start_session(DAY).id == "2026-09-24_02"


def test_recut_reuses_the_scans_calibration_and_typed_date(archive, tmp_path):
    session = archive.start_session(DAY)
    session.calibrate(make_scan([], glass_dust=[(640, 1100)], seed=5), DPI)
    album = archive.source("Album")
    result = session.add_scan(
        album,
        make_scan(TWO_PRINTS, glass_dust=[(640, 1100)]),
        DPI,
        typed=PhotoDate(1984),
    )

    Archive(tmp_path).source("Album").recut(result.scan)

    entries = _record(album)["scans"][0]["extracts"]
    assert [e["dust_repaired"] for e in entries] == [0, 1]
    assert {e["date"] for e in entries} == {"1984"}


# --- Backs -----------------------------------------------------------------------


def test_back_pass_pairs_backs_with_fronts_and_reads_their_date(archive, reader, tmp_path):
    session, album = archive.start_session(DAY), archive.source("Album")
    front = session.add_scan(album, make_scan(TWO_PRINTS), DPI)
    moved = [FakePrint((620, 1180), (300, 450), angle=3), FakePrint((280, 320), (450, 300))]
    reader.text = ["KODAK 12.08.79"]

    back = session.add_back(album, front.scan, make_scan(moved, seed=9), DPI)

    assert back.matched == {
        "album_s001_p01": "album_s001_p01_back",
        "album_s001_p02": "album_s001_p02_back",
    }
    assert back.unmatched == []
    assert (tmp_path / "archive/album/backs/album_s001_p01_back.tif").exists()
    assert (tmp_path / "archive/album/scans/album_s001_back.tif").exists()
    assert not list((tmp_path / "photos").rglob("*_back*"))  # never in Ugreen's tree
    entry = _record(album)["scans"][0]["extracts"][0]
    assert (entry["date"], entry["date_source"], entry["back"]) == (
        "1979-08-12",
        "ocr-back",
        "album_s001_p01_back",
    )
    assert _original_date(tmp_path / "photos/album/album_s001_p01.jpg") == "1979:08:12 12:00:00"


def test_a_back_that_matches_nothing_is_kept_and_reported(archive, tmp_path):
    session, album = archive.start_session(DAY), archive.source("Album")
    front = session.add_scan(album, make_scan([FakePrint((300, 300), (450, 300))]), DPI)
    far = [FakePrint((300, 300), (450, 300)), FakePrint((700, 1300), (300, 450))]

    back = session.add_back(album, front.scan, make_scan(far), DPI)

    assert back.unmatched == ["album_s001_back_unmatched_01"]
    assert (tmp_path / "archive/album/backs/album_s001_back_unmatched_01.tif").exists()


# --- Rotating --------------------------------------------------------------------


def test_rotate_turns_master_and_photo_from_either_path(archive, tmp_path):
    album = archive.source("Album", estimate=PhotoDate(1985))
    name = archive.start_session(DAY).add_scan(album, make_scan(TWO_PRINTS), DPI).extracts[0]
    master = tmp_path / f"archive/album/masters/{name}.tif"
    height, width = tifffile.imread(master).shape[:2]

    archive.rotate(tmp_path / f"photos/album/{name}.jpg", 90)

    assert tifffile.imread(master).shape[:2] == (width, height)
    with Image.open(tmp_path / f"photos/album/{name}.jpg") as img:
        assert img.size == (height, width)
    assert _original_date(tmp_path / f"photos/album/{name}.jpg") == "1985:01:01 12:00:00"


def test_16_bit_scans_give_16_bit_masters(archive, tmp_path):
    album = archive.source("Album")
    scan = make_scan(TWO_PRINTS).astype(np.uint16) * 257

    name = archive.start_session(DAY).add_scan(album, scan, DPI).extracts[0]

    assert tifffile.imread(tmp_path / f"archive/album/masters/{name}.tif").dtype == np.uint16
