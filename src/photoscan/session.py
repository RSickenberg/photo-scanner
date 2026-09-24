"""A Session on disk: one folder of Scans and their Extracts, under one Label.

<root>/<YYYY-MM-DD>_<label-slug>/
    session.json      label, date, and a record of every Scan and its Extracts
    scans/<slug>_s001.tif
    extracts/<slug>_s001_p01.tif  (+ .jpg)
"""

import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np

from photoscan.detect import cut, find_prints
from photoscan.imagefiles import Meta, read_tiff, write_jpeg, write_tiff

_SCAN_NUMBER = re.compile(r"_s(\d{3,})(?:_p\d+)?\.\w+$")


@dataclass(frozen=True)
class CutSettings:
    min_side_cm: float = 2.5
    inset_px: int = 2
    jpeg_quality: int = 95


DEFAULT_CUT = CutSettings()


@dataclass(frozen=True)
class ScanResult:
    scan: Path
    extracts: list[Path]


class Session:
    def __init__(
        self,
        path: Path,
        label: str,
        day: date,
        settings: CutSettings,
        next_number: int,
        record: dict,
    ):
        self.path = path
        self.label = label
        self.day = day
        self.settings = settings
        self._slug = path.name.split("_", 1)[1]
        self._next_number = next_number
        self._record = record

    @classmethod
    def open(
        cls,
        root: Path,
        label: str,
        day: date,
        *,
        known: Iterable[str] = (),
        settings: CutSettings = DEFAULT_CUT,
    ) -> "Session":
        """Create the Session folder, or reopen it and continue its numbering.

        `known` lists file names that exist only in the Backup (pruned locally),
        so their Scan numbers are never reused.
        """
        path = cls.folder(root, label, day)
        (path / "scans").mkdir(parents=True, exist_ok=True)
        (path / "extracts").mkdir(exist_ok=True)
        record_path = path / "session.json"
        record = json.loads(record_path.read_text()) if record_path.exists() else {}
        record |= {"label": label, "date": day.isoformat()}
        record.setdefault("scans", [])
        names = (
            [p.name for p in path.glob("*/*")]
            + [Path(k).name for k in known]
            + [f"{s['scan']}.tif" for s in record["scans"]]
        )
        numbers = [int(m.group(1)) for n in names if (m := _SCAN_NUMBER.search(n))]
        session = cls(path, label, day, settings, max(numbers, default=0) + 1, record)
        session._save_record()
        return session

    @staticmethod
    def folder(root: Path, label: str, day: date) -> Path:
        return root / f"{day.isoformat()}_{slugify(label)}"

    @classmethod
    def load(
        cls, path: Path, *, known: Iterable[str] = (), settings: CutSettings = DEFAULT_CUT
    ) -> "Session":
        """Reopen an existing Session folder."""
        info = json.loads((path / "session.json").read_text())
        return cls.open(
            path.parent, info["label"], date.fromisoformat(info["date"]),
            known=known, settings=settings,
        )  # fmt: skip

    def add_scan(self, scan: np.ndarray, dpi: int, *, scanner: str | None = None) -> ScanResult:
        """Keep the whole Scan, then cut it into Extracts (TIFF + JPEG each).

        `scanner` names the device, for the Session's record.
        """
        scan_path = self.path / "scans" / f"{self._slug}_s{self._next_number:03d}.tif"
        self._next_number += 1
        # The Session's date is the date of record; the clock only adds the time of day.
        meta = Meta(self.label, datetime.combine(self.day, datetime.now().time()), dpi)
        write_tiff(scan_path, scan, meta)
        extracts = self._extract(scan, scan_path, meta)
        self._record["scans"].append(
            {
                "scan": scan_path.stem,
                "scanned_at": _now(),
                "scanner": scanner,
                "dpi": dpi,
                "bits": 16 if scan.dtype == np.uint16 else 8,
                "extracts": [e.stem for e in extracts],
            }
        )
        self._save_record()
        return ScanResult(scan_path, extracts)

    def discard(self, scan_path: Path) -> None:
        """Throw away a Scan and its Extracts, e.g. when the preview shows a bad cut."""
        for extract in (self.path / "extracts").glob(f"{scan_path.stem}_p*"):
            extract.unlink()
        scan_path.unlink(missing_ok=True)
        self._record["scans"] = [s for s in self._record["scans"] if s["scan"] != scan_path.stem]
        self._save_record()
        if (m := _SCAN_NUMBER.search(scan_path.name)) and int(m.group(1)) == self._next_number - 1:
            self._next_number -= 1

    def recut(self, scan_path: Path) -> list[Path]:
        """Redo the Extracts of an existing Scan, e.g. after tuning detection."""
        scan, meta = read_tiff(scan_path)
        for old in (self.path / "extracts").glob(f"{scan_path.stem}_p*"):
            old.unlink()
        extracts = self._extract(scan, scan_path, Meta(self.label, meta.created, meta.dpi))
        for entry in self._record["scans"]:
            if entry["scan"] == scan_path.stem:
                entry["extracts"] = [e.stem for e in extracts]
                entry["recut_at"] = _now()
        self._save_record()
        return extracts

    def _save_record(self) -> None:
        scans = self._record["scans"]
        self._record["totals"] = {
            "scans": len(scans),
            "extracts": sum(len(s["extracts"]) for s in scans),
        }
        (self.path / "session.json").write_text(
            json.dumps(self._record, ensure_ascii=False, indent=2)
        )

    def _extract(self, scan: np.ndarray, scan_path: Path, meta: Meta) -> list[Path]:
        s = self.settings
        extracts = []
        regions = find_prints(scan, meta.dpi, min_side_cm=s.min_side_cm)
        for i, region in enumerate(regions, start=1):
            image = cut(scan, region, inset_px=s.inset_px)
            tif = self.path / "extracts" / f"{scan_path.stem}_p{i:02d}.tif"
            write_tiff(tif, image, meta)
            write_jpeg(tif.with_suffix(".jpg"), image, meta, quality=s.jpeg_quality)
            extracts.append(tif)
        return extracts


def rotate_extract(path: Path, degrees: int, *, jpeg_quality: int = 95) -> None:
    """Rotate an Extract clockwise; the JPEG is re-made from the lossless TIFF."""
    if degrees % 90:
        raise ValueError("rotation must be a multiple of 90 degrees")
    tif = path.with_suffix(".tif")
    image, meta = read_tiff(tif)
    image = np.ascontiguousarray(np.rot90(image, k=-(degrees // 90)))
    write_tiff(tif, image, meta)
    write_jpeg(tif.with_suffix(".jpg"), image, meta, quality=jpeg_quality)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(label: str) -> str:
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_label.lower()).strip("-") or "untitled"
