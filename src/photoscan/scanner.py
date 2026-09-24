"""Getting a Scan off the scanner: the one module that knows about SANE (ADR 0001)."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

import numpy as np
import tifffile


class ScannerError(Exception):
    pass


class Scanner(Protocol):
    def scan(self, dpi: int, *, deep: bool = False) -> np.ndarray:
        """One pass over the whole glass, as an RGB array (uint16 when `deep`)."""
        ...


class SaneScanner:
    """Drives `scanimage` from Homebrew's sane-backends (pixma backend for the LiDE 400)."""

    def __init__(self, device: str | None = None, run=subprocess.run):
        self._device = device
        self._run = run

    def scan(self, dpi: int, *, deep: bool = False) -> np.ndarray:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "scan.tif"
            result = self._run(self.command(dpi, deep, out), capture_output=True, text=True)
            if result.returncode != 0 or not out.exists():
                raise ScannerError(result.stderr.strip() or "scanimage produced no image")
            return tifffile.imread(out)

    def command(self, dpi: int, deep: bool, out: Path) -> list[str]:
        cmd = [_scanimage()]
        if self._device:
            cmd += ["--device-name", self._device]
        return cmd + [
            "--format=tiff",
            "--mode", "Color",
            "--resolution", str(dpi),
            "--depth", "16" if deep else "8",
            "--output-file", str(out),
        ]  # fmt: skip

    def devices(self) -> list[str]:
        result = self._run([_scanimage(), "--list-devices"], capture_output=True, text=True)
        return parse_devices(result.stdout)


def parse_devices(listing: str) -> list[str]:
    """Device names from `scanimage -L`, e.g. "device `pixma:04A91912' is a CANON ..."."""
    return re.findall(r"device [`'](.+?)' is a", listing)


def _scanimage() -> str:
    path = shutil.which("scanimage")
    if not path:
        raise ScannerError("scanimage not found: install it with `brew install sane-backends`")
    return path
