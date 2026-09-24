"""User settings, from ~/.config/photoscan/config.toml (or $PHOTOSCAN_CONFIG)."""

import os
import tomllib
from dataclasses import dataclass
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
    backend: str = "sane"
    device: str | None = None
    cut: CutSettings = CutSettings()


def config_path() -> Path:
    return Path(os.environ.get("PHOTOSCAN_CONFIG", DEFAULT_PATH)).expanduser()


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        return Config()
    raw = tomllib.loads(path.read_text())
    defaults = Config()
    return Config(
        output_dir=Path(raw.get("output_dir", defaults.output_dir)).expanduser(),
        nas_dir=Path(raw["nas_dir"]).expanduser() if raw.get("nas_dir") else None,
        dpi=int(raw.get("dpi", defaults.dpi)),
        back_dpi=int(raw.get("back_dpi", defaults.back_dpi)),
        backend=raw.get("backend", defaults.backend),
        device=raw.get("device"),
        cut=CutSettings(
            min_side_cm=float(raw.get("min_print_cm", defaults.cut.min_side_cm)),
            inset_px=int(raw.get("inset_px", defaults.cut.inset_px)),
            jpeg_quality=int(raw.get("jpeg_quality", defaults.cut.jpeg_quality)),
        ),
    )
