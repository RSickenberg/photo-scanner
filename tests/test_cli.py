import json

import cv2
import pytest
import tifffile
from PIL import ExifTags, Image
from typer.testing import CliRunner

from photoscan import cli
from photoscan.archive import Archive
from tests.synthetic import FakePrint, make_scan

TWO_PRINTS = [FakePrint((300, 300), (450, 300)), FakePrint((600, 1200), (300, 450))]


class FakeScanner:
    """First Scan: the empty glass (calibration). Then two Prints each time, with a
    new picture on each: a Back pass shows them flipped, not the same fronts."""

    name = "fake:scanner"

    def __init__(self):
        self.calls = 0

    def scan(self, dpi, *, deep=False):
        self.calls += 1
        if self.calls == 1:
            image = make_scan([], glass_dust=[(1100, 150)])
        else:
            image = make_scan(TWO_PRINTS, seed=self.calls)
        # The synthetic Scans are drawn at 150 dpi; like a real scanner, other
        # resolutions give bigger or smaller images of the same glass.
        return cv2.resize(image, None, fx=dpi / 150, fy=dpi / 150, interpolation=cv2.INTER_AREA)


class Reader:
    text: list[str] = []

    def __call__(self, image):
        return list(self.text)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    local, nas = tmp_path / "local", tmp_path / "nas"
    nas.mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'output_dir = "{local}"\nnas_dir = "{nas}"\ndpi = 150\nback_dpi = 75\n')
    monkeypatch.setenv("PHOTOSCAN_CONFIG", str(cfg))
    scanner, reader = FakeScanner(), Reader()
    monkeypatch.setattr(cli, "make_scanner", lambda _: scanner)
    monkeypatch.setattr(
        cli, "make_archive", lambda cfg: Archive(cfg.output_dir, settings=cfg.cut, reader=reader)
    )
    return local, nas, scanner, reader


def run(*args, input=""):
    result = CliRunner().invoke(cli.app, list(args), input=input)
    assert result.exit_code == 0, result.output
    return result


def _source_record(root, slug):
    return json.loads((root / "archive" / slug / "source.json").read_text())


def _original_date(jpg):
    with Image.open(jpg) as img:
        return img.getexif().get_ifd(ExifTags.IFD.Exif).get(0x9003)


def test_session_creates_a_source_calibrates_scans_and_backs_up(setup):
    local, nas, scanner, _ = setup

    # new Source's rough date, calibrate, scan twice, finish
    result = run("session", "Album Grand-mère", input="1970s\n\n\n\nq\n")

    assert scanner.calls == 3
    assert "Done: 4 Extract(s)" in result.output
    photos = sorted(p.name for p in (nas / "photos/album-grand-mere").iterdir())
    assert photos == [
        "album-grand-mere_s001_p01.jpg", "album-grand-mere_s001_p02.jpg",
        "album-grand-mere_s002_p01.jpg", "album-grand-mere_s002_p02.jpg",
    ]  # fmt: skip
    assert _original_date(nas / "photos/album-grand-mere" / photos[0]) == "1970:01:01 12:00:00"
    record = _source_record(local, "album-grand-mere")
    assert record["totals"] == {"scans": 2, "extracts": 4, "dated": 4, "undated": 0}
    assert {s["calibration"] for s in record["scans"]} == {record["scans"][0]["calibration"]}
    assert list(nas.glob("archive/_calibrations/*.tif"))


def test_existing_sources_are_offered_by_number(setup):
    local, _, _, _ = setup
    run("session", "Album", "--no-calibrate", input="\n\n\nq\n")

    result = run("session", "--no-calibrate", input="1\n\nq\n")

    assert "1. Album" in result.output
    # First run: s001 (the fake's empty glass) and s002; this run adds s003 to the same Source.
    assert [s["scan"] for s in _source_record(local, "album")["scans"]][-1] == "album_s003"


def test_d_dates_the_latest_scan_only_and_is_not_carried_over(setup):
    local, _, _, _ = setup

    run(
        "session", "Album", "--no-calibrate",
        # estimate, s001 (the fake's empty glass), s002, d 1984 (for s002), s003,
        # o -> new Box (no estimate), Box's s001
        input="\n\n\nd\n1984\n\no\nBox\n\n\nq\n",
    )  # fmt: skip

    album = {s["scan"]: [e["date"] for e in s["extracts"]] for s in
             _source_record(local, "album")["scans"]}  # fmt: skip
    assert album == {"album_s001": [], "album_s002": ["1984", "1984"], "album_s003": [None, None]}
    box = _source_record(local, "box")["scans"]
    assert [e["date"] for s in box for e in s["extracts"]] == [None, None]


def test_d_at_the_start_of_a_session_dates_the_previous_sessions_last_scan(setup):
    local, _, _, _ = setup
    run("session", "Album", "--no-calibrate", input="\n\n\nq\n")  # s001 (empty), s002

    result = run("session", "Album", "--no-calibrate", input="d\n~1990\nq\n")

    assert "album_s002" in result.output
    items = _source_record(local, "album")["scans"][-1]["extracts"]
    assert {(e["date"], e["date_source"]) for e in items} == {("ca. 1990", "scan")}


def test_d_says_which_extracts_keep_their_own_date(setup):
    local, _, _, reader = setup
    run("session", "Album", "--no-calibrate", input="\n\n\nq\n")  # s001 (empty), s002
    reader.text = ["KODAK 12.08.79"]
    run("session", "Album", "--no-calibrate", input="\nb\n\nq\n")  # s003, dated by its Backs

    result = run("session", "Album", "--no-calibrate", input="d\n1985\nq\n")

    assert "2 kept their own date" in result.output
    items = _source_record(local, "album")["scans"][-1]["extracts"]
    assert {e["date"] for e in items} == {"1979-08-12"}


def test_d_before_any_scan_in_a_new_source(setup):
    result = run("session", "Empty", "--no-calibrate", input="\nd\nq\n")
    assert "No Scan in 'Empty' yet" in result.output


def test_back_pass_reads_the_lab_stamp(setup):
    local, _, _, reader = setup
    run("session", "Album", "--no-calibrate", input="\n\n\nq\n")  # s001 = empty glass
    reader.text = ["KODAK 12.08.79"]

    result = run("session", "Album", "--no-calibrate", input="\nb\n\nq\n")

    assert "2 Back(s) matched" in result.output
    items = _source_record(local, "album")["scans"][-1]["extracts"]
    assert {(e["date"], e["date_source"]) for e in items} == {("1979-08-12", "ocr-back")}


def test_rejected_preview_discards_the_scan(setup, monkeypatch):
    local, _, _, _ = setup
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)  # don't open Preview.app

    run("session", "Album", "--preview", input="\n\n\nr\n\n\nq\n")

    assert [s["scan"] for s in _source_record(local, "album")["scans"]] == ["album_s001"]


def test_date_command_restamps_extracts_and_estimates(setup):
    local, nas, _, _ = setup
    run("session", "Album", "--no-calibrate", input="\n\n\nq\n")
    photo = local / "photos/album/album_s002_p01.jpg"

    run("date", "~1983", str(photo))
    assert _original_date(photo) == "1983:01:01 12:00:00"

    run("date", "1960s", "--source", "Album")
    other = local / "photos/album/album_s002_p02.jpg"
    assert _original_date(other) == "1960:01:01 12:00:00"
    assert _original_date(photo) == "1983:01:01 12:00:00"  # typed date kept

    listing = run("dates", "Album").output
    assert "ca. 1983" in listing
    assert "1960s" in listing


def test_rotate_command(setup):
    local, _, _, _ = setup
    run("session", "Album", "--no-calibrate", input="\n\n\nq\n")

    run("rotate", str(local / "photos/album/album_s002_p01.jpg"), "--degrees", "180")


def test_sync_shows_what_it_copies(setup, tmp_path, monkeypatch):
    local, nas, _, _ = setup
    cfg = tmp_path / "offline.toml"
    cfg.write_text(f'output_dir = "{local}"\nnas_dir = "{tmp_path / "unmounted"}"\ndpi = 150\n')
    monkeypatch.setenv("PHOTOSCAN_CONFIG", str(cfg))
    run("session", "Album", "--no-calibrate", input="\n\n\nq\n")  # NAS absent: nothing copied
    (tmp_path / "unmounted").mkdir()

    result = run("sync")

    assert "Copying" in result.output
    assert "file(s) copied, 0 failed" in result.output
    assert list((tmp_path / "unmounted/photos/album").glob("*.jpg"))


def test_prune_shows_what_it_verifies(setup):
    local, _, _, _ = setup
    run("session", "Album", "--no-calibrate", input="\n\n\nq\n")  # backed up on the way

    result = run("prune", "--yes")

    assert "Verifying" in result.output
    assert not list(local.glob("photos/*/*.jpg"))


def test_compact_shrinks_local_files_and_the_nas_copies_of_pruned_ones(setup, monkeypatch):
    local, nas, _, _ = setup
    write = tifffile.TiffWriter.write
    with monkeypatch.context() as m:  # TIFFs as versions before 2.3 wrote them
        m.setattr(
            tifffile.TiffWriter,
            "write",
            lambda self, *a, **k: write(self, *a, **{**k, "predictor": None}),
        )
        run("session", "Album", "--no-calibrate", input="\n\n\nq\n")  # s001, s002
        run("prune", "--yes")
        run("session", "Album", "--no-calibrate", input="\nq\n")  # s003, still local

    result = run("compact")

    assert "file(s) compacted" in result.output
    for tiff in nas.glob("archive/album/*/*.tif"):
        with tifffile.TiffFile(tiff) as tif:
            assert tif.pages[0].predictor == 2, tiff.name
    kept = "archive/album/scans/album_s003.tif"
    assert (local / kept).read_bytes() == (nas / kept).read_bytes()  # synced
    assert not (local / "archive/album/scans/album_s002.tif").exists()  # still pruned


def test_forced_prune_warns_about_files_not_on_the_nas(setup, tmp_path, monkeypatch):
    local, _, _, _ = setup
    run("session", "Album", "--no-calibrate", input="\n\n\nq\n")
    cfg = tmp_path / "no-nas.toml"
    cfg.write_text(f'output_dir = "{local}"\n')  # no NAS configured at all
    monkeypatch.setenv("PHOTOSCAN_CONFIG", str(cfg))

    refused = CliRunner().invoke(cli.app, ["prune", "--force"], input="n\n")
    assert "NOT on the NAS" in refused.output
    assert list(local.glob("photos/*/*.jpg"))

    run("prune", "--force", "--yes")
    assert not list(local.glob("photos/*/*.jpg"))
    assert not list(local.glob("archive/*/scans/*"))
    assert (local / "archive/album/source.json").exists()  # records are kept


def test_a_recent_calibration_is_reused_without_asking(setup):
    local, _, scanner, _ = setup
    run("session", "Album", input="\n\nq\n")  # estimate, calibrate, finish
    assert scanner.calls == 1

    result = run("session", "Album", input="\nq\n")  # straight to scanning

    assert "Using the calibration from" in result.output
    assert "Calibration:" not in result.output
    assert scanner.calls == 2  # one Scan, no calibration pass


@pytest.mark.parametrize("args", [["dates", "Typo"], ["date", "1985", "--source", "Typo"]])
def test_an_unknown_source_is_refused_not_created(setup, args):
    local, _, _, _ = setup
    run("session", "Album", "--no-calibrate", input="\nq\n")

    result = CliRunner().invoke(cli.app, args)

    assert result.exit_code != 0
    assert "No Source named 'Typo'" in result.output
    assert "Album" in result.output  # the known ones are listed
    assert not (local / "archive/typo").exists()


def test_a_bad_config_value_is_reported_clearly(setup, tmp_path, monkeypatch):
    cfg = tmp_path / "bad.toml"
    cfg.write_text("inset_px = 1.5\n")
    monkeypatch.setenv("PHOTOSCAN_CONFIG", str(cfg))

    result = CliRunner().invoke(cli.app, ["dates"])

    assert result.exit_code != 0
    assert "inset_px must be a whole number" in result.output
