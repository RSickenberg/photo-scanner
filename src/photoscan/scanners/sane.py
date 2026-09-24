"""Scanners driven through SANE's `scanimage` (Homebrew `sane-backends`, ADR 0001).

SANE backends name their options differently: the LiDE 400 (pixma) picks
16 bits per channel with `--mode "48 bits color"`, others use `--mode Color
--depth 16`. So nothing is hard-coded: each scanner's options are read once
with `scanimage --all-options` and the command is built from them.
"""

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile

from photoscan.scanners import ScannerError


@dataclass(frozen=True)
class Options:
    """What a device offers, as listed by `scanimage --all-options`."""

    modes: tuple[str, ...]
    depths: tuple[str, ...]


class SaneScanner:
    def __init__(self, device: str | None = None, run=subprocess.run):
        self._device = device
        self._run = run
        self._options: Options | None = None

    @property
    def name(self) -> str | None:
        """The device, looked up (`scanimage -L`) if none is configured; None if absent."""
        if not self._device:
            try:
                self._resolve_device()
            except ScannerError:
                return None
        return self._device

    def scan(self, dpi: int, *, deep: bool = False) -> np.ndarray:
        device = self._resolve_device()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "scan.tif"
            cmd = build_command(device, self._device_options(device), dpi, deep, out)
            result = self._run(cmd, capture_output=True, text=True)
            if result.returncode != 0 or not out.exists():
                raise ScannerError(result.stderr.strip() or "scanimage produced no image")
            return tifffile.imread(out)

    def devices(self) -> list[str]:
        result = self._run([_scanimage(), "--list-devices"], capture_output=True, text=True)
        return parse_devices(result.stdout)

    def _resolve_device(self) -> str:
        """The configured device, else the first one SANE finds (then remembered)."""
        if not self._device:
            found = self.devices()
            if not found:
                raise ScannerError("No scanner found. Is it plugged in and switched on?")
            self._device = found[0]
        return self._device

    def _device_options(self, device: str) -> Options:
        if self._options is None:
            cmd = [_scanimage(), "--device-name", device, "--all-options"]
            result = self._run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise ScannerError(result.stderr.strip() or f"cannot read options of {device}")
            self._options = parse_options(result.stdout)
        return self._options


def build_command(device: str, options: Options, dpi: int, deep: bool, out: Path) -> list[str]:
    colour = _colour_mode(options.modes)
    if not deep:
        mode_args = ["--mode", colour]
    elif deep_mode := next((m for m in options.modes if "48" in m), None):
        mode_args = ["--mode", deep_mode]
    elif "16" in options.depths:
        mode_args = ["--mode", colour, "--depth", "16"]
    else:
        raise ScannerError(f"{device} can't scan at 16 bits per channel; drop --16bit")
    return [
        _scanimage(), "--device-name", device,
        "--format=tiff",
        *mode_args,
        "--resolution", str(dpi),
        "--output-file", str(out),
    ]  # fmt: skip


def parse_options(listing: str) -> Options:
    return Options(modes=_choices(listing, "mode"), depths=_choices(listing, "depth"))


def parse_devices(listing: str) -> list[str]:
    """Device names from `scanimage -L`, e.g. "device `pixma:04A91912' is a CANON ..."."""
    return re.findall(r"device [`'](.+?)' is a", listing)


def _choices(listing: str, option: str) -> tuple[str, ...]:
    """`    --mode auto|Color|48 bits color [Color]` -> ("auto", "Color", "48 bits color")."""
    match = re.search(rf"^\s*--{option} (.+?) \[", listing, re.MULTILINE)
    return tuple(match.group(1).split("|")) if match else ()


def _colour_mode(modes: tuple[str, ...]) -> str:
    for mode in modes:
        if mode.lower() in ("color", "colour"):
            return mode
    return "Color"  # SANE's standard name, if the listing was unexpected


def _scanimage() -> str:
    path = shutil.which("scanimage")
    if not path:
        raise ScannerError("scanimage not found: install it with `brew install sane-backends`")
    return path
