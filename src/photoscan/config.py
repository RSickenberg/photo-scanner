"""User settings, from ~/.config/photoscan/config.toml (or $PHOTOSCAN_CONFIG)."""

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from photoscan.archive import CutSettings

DEFAULT_PATH = Path("~/.config/photoscan/config.toml")

EXAMPLE = """\
# photoscan config: ~/.config/photoscan/config.toml (or $PHOTOSCAN_CONFIG).
# `photoscan config` creates it from this template (config.toml.example).

# Where Sessions are written first (fast, always available).
output_dir = "~/Pictures/photoscan"

# The mounted NAS share that holds the Backup. Mount it in Finder first
# (Go > Connect to Server, smb://...), then point this at /Volumes/<share>/...
# nas_dir = "/Volumes/photos/family-scans"

dpi = 600
back_dpi = 300       # Backs are only read for printed dates: 300 dpi takes half the time

# A calibration this recent (same scanner, same dpi) is reused instead of
# asking to scan the empty glass again. Press c in a Session to redo it.
calibration_max_age_minutes = 120
min_print_cm = 2.5   # shorter side; anything smaller is treated as dust
inset_px = 2         # cut this far inside each Print's edge
jpeg_quality = 95

# How scanners are driven. "sane" covers every scanner SANE supports
# (http://www.sane-project.org/sane-supported-devices.html).
backend = "sane"

# Only needed if several scanners are attached; see `photoscan devices`.
# Without it, the first scanner found is used.
# device = "pixma:04A91912"
"""


@dataclass(frozen=True)
class Config:
    output_dir: Path = Path("~/Pictures/photoscan").expanduser()
    nas_dir: Path | None = None
    dpi: int = 600
    back_dpi: int = 300
    calibration_max_age_minutes: int = 120
    backend: str = "sane"
    device: str | None = None
    cut: CutSettings = CutSettings()


class ConfigError(ValueError):
    pass


# Config file key -> (setting it fills, kind of value). The cut settings live
# in CutSettings; `min_print_cm` is its `min_side_cm`.
_KEYS = {
    "output_dir": ("output_dir", Path),
    "nas_dir": ("nas_dir", Path),
    "dpi": ("dpi", int),
    "back_dpi": ("back_dpi", int),
    "calibration_max_age_minutes": ("calibration_max_age_minutes", int),
    "backend": ("backend", str),
    "device": ("device", str),
    "min_print_cm": ("cut.min_side_cm", float),
    "inset_px": ("cut.inset_px", int),
    "jpeg_quality": ("cut.jpeg_quality", int),
}


def config_path() -> Path:
    return Path(os.environ.get("PHOTOSCAN_CONFIG", DEFAULT_PATH)).expanduser()


def load(path: Path | None = None) -> Config:
    """The settings from the config file; defaults for anything it doesn't set."""
    path = path or config_path()
    raw = tomllib.loads(path.read_text()) if path.exists() else {}
    top, cut = {}, {}
    for key, value in raw.items():
        if key not in _KEYS or value in ("", None):
            continue
        name, kind = _KEYS[key]
        target, name = (cut, name[4:]) if name.startswith("cut.") else (top, name)
        target[name] = _convert(key, value, kind)
    return replace(Config(**top), cut=CutSettings(**cut))


def _convert(key: str, value, kind: type):
    if kind is Path:
        return Path(str(value)).expanduser()
    if kind is int:
        # 2 and 2.0 are fine; 1.5 or "600" are not silently turned into something else.
        if isinstance(value, bool) or not isinstance(value, int | float) or value != int(value):
            raise ConfigError(f"{key} must be a whole number, got {value!r}")
        return int(value)
    if kind is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"{key} must be a number, got {value!r}")
        return float(value)
    return str(value)
