"""User settings, from ~/.config/photoscan/config.toml (or $PHOTOSCAN_CONFIG)."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from photoscan.session import CutSettings

DEFAULT_PATH = Path("~/.config/photoscan/config.toml")

EXAMPLE = """\
# Where Sessions are written first (fast, always available).
output_dir = "~/Pictures/photoscan"

# The mounted NAS share that holds the Backup. Mount it in Finder first
# (Go > Connect to Server, smb://...), then point this at /Volumes/<share>/...
# nas_dir = "/Volumes/photos/family-scans"

dpi = 600
min_print_cm = 2.5   # shorter side; anything smaller is treated as dust
inset_px = 2         # cut this far inside each Print's edge
jpeg_quality = 95

# Only needed if several scanners are attached; see `photoscan devices`.
# device = "pixma:04A91912"
"""


@dataclass(frozen=True)
class Config:
    output_dir: Path = Path("~/Pictures/photoscan").expanduser()
    nas_dir: Path | None = None
    dpi: int = 600
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
        device=raw.get("device"),
        cut=CutSettings(
            min_side_cm=float(raw.get("min_print_cm", defaults.cut.min_side_cm)),
            inset_px=int(raw.get("inset_px", defaults.cut.inset_px)),
            jpeg_quality=int(raw.get("jpeg_quality", defaults.cut.jpeg_quality)),
        ),
    )
