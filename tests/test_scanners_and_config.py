import subprocess
from pathlib import Path

import numpy as np
import pytest
import tifffile

from photoscan.config import EXAMPLE, Config, load
from photoscan.scanners import ScannerError, create, sane
from photoscan.scanners.sane import SaneScanner, build_command, parse_devices, parse_options

# Trimmed `scanimage -A` output of the real Canon CanoScan LiDE 400 (pixma backend).
LIDE_400 = """
All options specific to device `pixma:04A91912_4FA05A':
    --resolution auto||75|150|300|600|1200|2400|4800dpi [75]
    --mode auto|Color|Gray|48 bits color|16 bits gray|Lineart [Color]
    --source Flatbed [Flatbed]
"""
# A scanner whose backend uses a separate --depth option (e.g. genesys, epson2).
WITH_DEPTH = """
All options specific to device `genesys:libusb:001:004':
    --mode Color|Gray|Lineart [Gray]
    --depth 8|16 [8]
    --resolution 75|150|300|600|1200dpi [300]
"""
NO_16_BIT = """
All options specific to device `hp5400:libusb:001:005':
    --mode Color [Color]
    --resolution 75|150|300|600|1200dpi [75]
"""
OUT = Path("/tmp/x.tif")


@pytest.fixture(autouse=True)
def fake_scanimage_on_path(monkeypatch):
    monkeypatch.setattr(sane.shutil, "which", lambda _: "/opt/homebrew/bin/scanimage")


def test_lide_400_command():
    cmd = build_command("pixma:04A91912", parse_options(LIDE_400), 600, False, OUT)
    assert cmd == [
        "/opt/homebrew/bin/scanimage", "--device-name", "pixma:04A91912",
        "--format=tiff", "--mode", "Color", "--resolution", "600",
        "--output-file", "/tmp/x.tif",
    ]  # fmt: skip


def test_lide_400_16_bit_uses_its_48_bit_colour_mode():
    cmd = build_command("pixma:04A91912", parse_options(LIDE_400), 600, True, OUT)
    assert cmd[cmd.index("--mode") + 1] == "48 bits color"
    assert "--depth" not in cmd


def test_scanner_with_a_depth_option_scans_colour_at_depth_16():
    cmd = build_command("genesys:x", parse_options(WITH_DEPTH), 600, True, OUT)
    assert cmd[cmd.index("--mode") + 1] == "Color"
    assert cmd[cmd.index("--depth") + 1] == "16"


def test_scanner_without_16_bit_refuses_deep_scans_clearly():
    with pytest.raises(ScannerError, match="16 bits"):
        build_command("hp5400:x", parse_options(NO_16_BIT), 600, True, OUT)


def _fake_scanimage(listing=LIDE_400, devices="device `pixma:04A91912' is a CANON LiDE 400\n"):
    calls = []

    def run(cmd, **_):
        calls.append(cmd)
        if "--list-devices" in cmd:
            return subprocess.CompletedProcess(cmd, 0, devices, "")
        if "--all-options" in cmd:
            return subprocess.CompletedProcess(cmd, 0, listing, "")
        tifffile.imwrite(cmd[cmd.index("--output-file") + 1], np.zeros((4, 5, 3), np.uint16))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return run, calls


def test_scan_uses_the_first_scanner_found_and_names_it():
    run, calls = _fake_scanimage()
    scanner = SaneScanner(run=run)

    image = scanner.scan(300, deep=True)

    assert image.shape == (4, 5, 3)
    assert scanner.name == "pixma:04A91912"
    assert calls[-1][calls[-1].index("--device-name") + 1] == "pixma:04A91912"


def test_options_are_read_once_per_scanner():
    run, calls = _fake_scanimage()
    scanner = SaneScanner(device="pixma:04A91912", run=run)
    scanner.scan(300)
    scanner.scan(300)
    assert sum("--all-options" in c for c in calls) == 1


def test_no_scanner_connected():
    run, _ = _fake_scanimage(devices="")
    with pytest.raises(ScannerError, match="No scanner found"):
        SaneScanner(run=run).scan(300)


def test_scanner_errors_are_surfaced():
    def failing_run(cmd, **_):
        return subprocess.CompletedProcess(cmd, 1, "", "scanimage: open of device failed")

    with pytest.raises(ScannerError, match="open of device failed"):
        SaneScanner(device="pixma:x", run=failing_run).scan(600)


def test_parse_devices():
    listing = "device `pixma:04A91912_4FA05A' is a CANON CanoScan LiDE 400 multi-function\n"
    assert parse_devices(listing) == ["pixma:04A91912_4FA05A"]


def test_create_picks_the_backend_by_name():
    assert isinstance(create("sane", "pixma:x"), SaneScanner)
    with pytest.raises(ScannerError, match="Unknown scanner backend"):
        create("twain", None)


def test_config_defaults_when_file_missing(tmp_path):
    config = load(tmp_path / "missing.toml")
    assert config.dpi == 600
    assert config.nas_dir is None
    assert config.backend == "sane"


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


def test_config_toml_example_matches_what_photoscan_config_writes():
    example = Path(__file__).parents[1] / "config.toml.example"
    assert example.read_text() == EXAMPLE


def test_config_toml_example_documents_the_real_defaults():
    assert load(Path(__file__).parents[1] / "config.toml.example") == Config()


def test_name_looks_the_scanner_up_before_any_scan():
    run, calls = _fake_scanimage()
    scanner = SaneScanner(run=run)

    assert scanner.name == "pixma:04A91912"
    assert not any("--output-file" in c for c in calls)


def test_name_is_none_when_no_scanner_is_connected():
    run, _ = _fake_scanimage(devices="")
    assert SaneScanner(run=run).name is None
