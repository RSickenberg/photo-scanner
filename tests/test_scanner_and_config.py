import subprocess
from pathlib import Path

import numpy as np
import pytest
import tifffile

from photoscan import scanner
from photoscan.config import load
from photoscan.scanner import SaneScanner, ScannerError, parse_devices


@pytest.fixture(autouse=True)
def fake_scanimage_on_path(monkeypatch):
    monkeypatch.setattr(scanner.shutil, "which", lambda _: "/opt/homebrew/bin/scanimage")


def test_scan_command_for_the_lide_400():
    cmd = SaneScanner(device="pixma:04A91912").command(600, False, Path("/tmp/x.tif"))
    assert cmd == [
        "/opt/homebrew/bin/scanimage", "--device-name", "pixma:04A91912",
        "--format=tiff", "--mode", "Color", "--resolution", "600",
        "--output-file", "/tmp/x.tif",
    ]  # fmt: skip


def test_16_bit_uses_the_pixma_48_bit_colour_mode():
    # The pixma backend has no --depth option; 16 bits per channel is a mode.
    cmd = SaneScanner().command(600, True, Path("/tmp/x.tif"))
    assert cmd[cmd.index("--mode") + 1] == "48 bits color"
    assert "--depth" not in cmd


def test_scan_reads_back_the_image_scanimage_wrote():
    def fake_run(cmd, **_):
        tifffile.imwrite(cmd[cmd.index("--output-file") + 1], np.zeros((4, 5, 3), np.uint16))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    image = SaneScanner(run=fake_run).scan(300, deep=True)
    assert image.shape == (4, 5, 3)


def test_scanner_errors_are_surfaced():
    def failing_run(cmd, **_):
        return subprocess.CompletedProcess(cmd, 1, "", "scanimage: no SANE devices found")

    with pytest.raises(ScannerError, match="no SANE devices"):
        SaneScanner(run=failing_run).scan(600)


def test_parse_devices():
    listing = "device `pixma:04A91912' is a CANON CanoScan LiDE 400 flatbed scanner\n"
    assert parse_devices(listing) == ["pixma:04A91912"]


def test_config_defaults_when_file_missing(tmp_path):
    config = load(tmp_path / "missing.toml")
    assert config.dpi == 600
    assert config.nas_dir is None


def test_config_reads_user_values(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        'output_dir = "~/scans"\nnas_dir = "/Volumes/photos"\ndpi = 300\ninset_px = 4\n'
    )

    config = load(path)

    assert config.output_dir == Path("~/scans").expanduser()
    assert config.nas_dir == Path("/Volumes/photos")
    assert config.dpi == 300
    assert config.cut.inset_px == 4
