import json

import pytest
from typer.testing import CliRunner

from photoscan import cli
from tests.synthetic import FakePrint, make_scan


class FakeScanner:
    """First Scan: the empty glass (calibration). Then two Prints each time."""

    name = "fake:scanner"

    def __init__(self):
        self.calls = 0

    def scan(self, dpi, *, deep=False):
        self.calls += 1
        if self.calls == 1:
            return make_scan([], glass_dust=[(1100, 150)])
        return make_scan([FakePrint((300, 300), (450, 300)), FakePrint((600, 1200), (300, 450))])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    local, nas = tmp_path / "local", tmp_path / "nas"
    nas.mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'output_dir = "{local}"\nnas_dir = "{nas}"\ndpi = 150\n')
    monkeypatch.setenv("PHOTOSCAN_CONFIG", str(cfg))
    scanner = FakeScanner()
    monkeypatch.setattr(cli, "make_scanner", lambda _: scanner)
    return local, nas, scanner


def test_a_session_scans_until_q_and_backs_everything_up(setup):
    local, nas, scanner = setup

    result = CliRunner().invoke(cli.app, ["session", "Grandma"], input="\n\n\nq\n")

    assert result.exit_code == 0, result.output
    assert scanner.calls == 3  # calibration + 2 Scans
    assert "1 dust speck(s)" in result.output
    assert "Done: 4 Extract(s)" in result.output
    extracts = sorted(p.name for p in nas.glob("*/extracts/*.tif"))
    assert extracts == [
        "grandma_s001_p01.tif", "grandma_s001_p02.tif",
        "grandma_s002_p01.tif", "grandma_s002_p02.tif",
    ]  # fmt: skip
    record = json.loads(next(nas.glob("*/session.json")).read_text())
    assert record["totals"] == {"scans": 2, "extracts": 4}
    assert {s["scanner"] for s in record["scans"]} == {"fake:scanner"}
    assert {s["calibration"] for s in record["scans"]} == {"cal_01"}
    assert list(nas.glob("*/calibration/cal_01.tif"))


def test_rejected_preview_discards_the_scan(setup, monkeypatch):
    local, _, _ = setup
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)  # don't open Preview.app

    args = ["session", "Grandma", "--preview"]
    result = CliRunner().invoke(cli.app, args, input="\n\nr\n\n\nq\n")

    assert result.exit_code == 0, result.output
    assert [p.name for p in local.glob("*/scans/*")] == ["grandma_s001.tif"]


def test_rotate_command(setup):
    local, _, _ = setup
    # The fake's first Scan is always the empty glass, so scan twice.
    CliRunner().invoke(cli.app, ["session", "Grandma", "--no-calibrate"], input="\n\nq\n")
    extract = next(local.glob("*/extracts/*_p01.jpg"))

    result = CliRunner().invoke(cli.app, ["rotate", str(extract), "--degrees", "180"])

    assert result.exit_code == 0, result.output


def test_calibration_can_be_skipped_then_done_mid_session(setup):
    local, _, _ = setup

    result = CliRunner().invoke(cli.app, ["session", "Grandma"], input="s\n\nc\n\nq\n")

    assert result.exit_code == 0, result.output
    record = json.loads(next(local.glob("*/session.json")).read_text())
    # Skipped at the start, so the first Scan is uncalibrated; `c` then calibrates.
    assert record["scans"][0]["calibration"] is None
    assert [c["id"] for c in record["calibrations"]] == ["cal_01"]
