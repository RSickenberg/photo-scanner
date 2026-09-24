import json

import pytest
from PIL import ExifTags, Image
from typer.testing import CliRunner

from photoscan import cli
from photoscan.archive import Archive
from tests.synthetic import FakePrint, make_scan

TWO_PRINTS = [FakePrint((300, 300), (450, 300)), FakePrint((600, 1200), (300, 450))]


class FakeScanner:
    """First Scan: the empty glass (calibration). Then two Prints each time."""

    name = "fake:scanner"

    def __init__(self):
        self.calls = 0

    def scan(self, dpi, *, deep=False):
        self.calls += 1
        if self.calls == 1:
            return make_scan([], glass_dust=[(1100, 150)])
        return make_scan(TWO_PRINTS)


class Reader:
    text: list[str] = []

    def __call__(self, image):
        return list(self.text)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    local, nas = tmp_path / "local", tmp_path / "nas"
    nas.mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'output_dir = "{local}"\nnas_dir = "{nas}"\ndpi = 150\n')
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


def test_d_sets_a_date_and_o_switches_source_mid_session(setup):
    local, _, _, _ = setup

    run(
        "session", "Album", "--no-calibrate",
        # estimate, (1st call is empty glass), d 1984, scan, o -> new Box (no estimate), scan
        input="\n\nd\n1984\n\no\nBox\n\n\nq\n",
    )  # fmt: skip

    album = _source_record(local, "album")["scans"]
    assert [e["date"] for s in album for e in s["extracts"]] == ["1984", "1984"]
    box = _source_record(local, "box")["scans"]
    assert [e["date"] for s in box for e in s["extracts"]] == [None, None]


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
