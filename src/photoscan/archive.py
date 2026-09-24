"""The archive on disk, organised by Source (ADR 0002).

    <root>/photos/<source>/<source>_s001_p01.jpg     fronts only: point Ugreen Photos here
    <root>/archive/<source>/source.json               the Source's record (never pruned)
    <root>/archive/<source>/scans/<source>_s001.tif   whole Scans (+ _back.tif)
    <root>/archive/<source>/masters/<source>_s001_p01.tif   lossless Extracts
    <root>/archive/<source>/backs/<source>_s001_p01_back.tif (+ .jpg)
    <root>/archive/_sessions/<date>_01.json           each sitting: calibrations, Scans made
    <root>/archive/_calibrations/<date>_01_cal_01.tif  empty-glass Scans

The Photo date lives in each Extract's metadata, never in names, so it can be
corrected without renaming (and re-uploading) anything.
"""

import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np

from photoscan import detect
from photoscan.dates import PhotoDate, choose_date
from photoscan.detect import Calibration, Region, cut, find_prints, match_backs, repair_dust
from photoscan.imagefiles import Meta, read_tiff, write_jpeg, write_tiff

Reader = Callable[[np.ndarray], list[str]]


@dataclass(frozen=True)
class CutSettings:
    min_side_cm: float = 2.5
    inset_px: int = 2
    jpeg_quality: int = 95


DEFAULT_CUT = CutSettings()


@dataclass(frozen=True)
class ScanResult:
    scan: str
    extracts: list[str]


@dataclass(frozen=True)
class BackResult:
    matched: dict[str, str]  # Extract name -> its Back's name
    unmatched: list[str]


class Archive:
    def __init__(
        self, root: Path, *, settings: CutSettings = DEFAULT_CUT, reader: Reader | None = None
    ):
        self.root = root
        self.settings = settings
        if reader is None:
            from photoscan.ocr import read_text as reader
        self.reader = reader
        self.photos = root / "photos"
        self.archive = root / "archive"
        self._calibrations: dict[str, Calibration] = {}

    def sources(self) -> list["Source"]:
        records = sorted(self.archive.glob("[!_]*/source.json"))
        return [Source(self, json.loads(r.read_text())) for r in records]

    def source(self, name: str, *, estimate: PhotoDate | None = None) -> "Source":
        """Open a Source, creating it (with its date estimate) if it's new."""
        path = self.archive / slugify(name) / "source.json"
        if path.exists():
            return Source(self, json.loads(path.read_text()))
        record = {"name": name, "estimate": str(estimate) if estimate else None, "scans": []}
        source = Source(self, record)
        source.save()
        return source

    def start_session(self, day: date | None = None) -> "Session":
        day = day or date.today()
        folder = self.archive / "_sessions"
        folder.mkdir(parents=True, exist_ok=True)
        number = len(list(folder.glob(f"{day.isoformat()}_*.json"))) + 1
        session = Session(self, f"{day.isoformat()}_{number:02d}")
        session.save()
        return session

    def calibration(self, cal_id: str | None) -> Calibration | None:
        if cal_id is None:
            return None
        if cal_id not in self._calibrations:
            empty, meta = read_tiff(self.archive / "_calibrations" / f"{cal_id}.tif")
            self._calibrations[cal_id] = detect.calibrate(empty, meta.dpi)
        return self._calibrations[cal_id]

    def locate(self, path: Path) -> tuple["Source", str]:
        """The Source and Extract (or Scan) name behind a photo, master or Scan path."""
        path = path.resolve()
        for folder in (self.photos.resolve(), self.archive.resolve()):
            if path.is_relative_to(folder):
                slug = path.relative_to(folder).parts[0]
                return self.source_by_slug(slug), path.stem
        raise ValueError(f"{path} is not in the archive at {self.root}")

    def source_by_slug(self, slug: str) -> "Source":
        return Source(self, json.loads((self.archive / slug / "source.json").read_text()))

    def rotate(self, path: Path, degrees: int) -> None:
        """Turn an Extract clockwise; its photo is re-made from the lossless master."""
        if degrees % 90:
            raise ValueError("rotation must be a multiple of 90 degrees")
        source, name = self.locate(path)
        master = source.master(name)
        image, meta = read_tiff(master)
        image = np.ascontiguousarray(np.rot90(image, k=-(degrees // 90)))
        write_tiff(master, image, meta)
        write_jpeg(source.photo(name), image, meta, quality=self.settings.jpeg_quality)


class Session:
    """One sitting: its calibrations and the Scans made, across Sources."""

    def __init__(self, archive: Archive, session_id: str):
        self.archive = archive
        self.id = session_id
        self.calibration_id: str | None = None
        self._record = {"id": session_id, "started": _now(), "calibrations": [], "scans": []}

    @property
    def calibration(self) -> Calibration | None:
        return self.archive.calibration(self.calibration_id)

    def calibrate(self, empty: np.ndarray, dpi: int, *, scanner: str | None = None) -> Calibration:
        """Learn the empty glass (background, dust); the Session's next Scans use it."""
        cal_id = f"{self.id}_cal_{len(self._record['calibrations']) + 1:02d}"
        folder = self.archive.archive / "_calibrations"
        folder.mkdir(parents=True, exist_ok=True)
        write_tiff(folder / f"{cal_id}.tif", empty, Meta("Calibration", datetime.now(), dpi))
        calibration = detect.calibrate(empty, dpi)
        self.archive._calibrations[cal_id] = calibration
        self._record["calibrations"].append(
            {
                "id": cal_id,
                "calibrated_at": _now(),
                "scanner": scanner,
                "dpi": dpi,
                "background_lab": [round(c, 1) for c in calibration.colour],
                "noise": round(calibration.noise, 2),
                "threshold": round(calibration.threshold, 2),
                "dust_specks": calibration.dust_specks,
            }
        )
        self.calibration_id = cal_id
        self.save()
        return calibration

    def add_scan(
        self,
        source: "Source",
        scan: np.ndarray,
        dpi: int,
        *,
        scanner: str | None = None,
        typed: PhotoDate | None = None,
    ) -> ScanResult:
        result = source.add_scan(
            scan,
            dpi,
            session=self.id,
            scanner=scanner,
            calibration=self.calibration_id,
            typed=typed,
        )
        self._record["scans"].append({"source": source.slug, "scan": result.scan})
        self.save()
        return result

    def add_back(self, source: "Source", scan: str, back: np.ndarray, dpi: int) -> BackResult:
        return source.add_back(scan, back, dpi, calibration=self.calibration_id)

    def save(self) -> None:
        path = self.archive.archive / "_sessions" / f"{self.id}.json"
        path.write_text(json.dumps(self._record, ensure_ascii=False, indent=2))


class Source:
    def __init__(self, archive: Archive, record: dict):
        self.archive = archive
        self._record = record
        self._record.setdefault("scans", [])
        self.name: str = record["name"]
        self.slug = slugify(self.name)
        self.path = archive.archive / self.slug

    @property
    def estimate(self) -> PhotoDate | None:
        return PhotoDate.parse(self._record["estimate"]) if self._record.get("estimate") else None

    @property
    def scans(self) -> list[dict]:
        return self._record["scans"]

    # --- paths -----------------------------------------------------------------

    def scan_file(self, scan: str) -> Path:
        return self.path / "scans" / f"{scan}.tif"

    def master(self, extract: str) -> Path:
        return self.path / "masters" / f"{extract}.tif"

    def photo(self, extract: str) -> Path:
        return self.archive.photos / self.slug / f"{extract}.jpg"

    def back(self, name: str, suffix: str = ".tif") -> Path:
        return self.path / "backs" / f"{name}{suffix}"

    # --- changes ---------------------------------------------------------------

    def add_scan(
        self,
        scan: np.ndarray,
        dpi: int,
        *,
        session: str | None = None,
        scanner: str | None = None,
        calibration: str | None = None,
        typed: PhotoDate | None = None,
    ) -> ScanResult:
        name = f"{self.slug}_s{self._next_number():03d}"
        entry = {
            "scan": name,
            "scanned_at": _now(),
            "session": session,
            "scanner": scanner,
            "dpi": dpi,
            "bits": 16 if scan.dtype == np.uint16 else 8,
            "calibration": calibration,
            "typed_date": str(typed) if typed else None,
            "extracts": [],
            "back_scan": None,
            "unmatched_backs": [],
        }
        self.scan_file(name).parent.mkdir(parents=True, exist_ok=True)
        write_tiff(self.scan_file(name), scan, self._meta(entry))
        entry["extracts"] = self._cut(scan, entry)
        self.scans.append(entry)
        self.save()
        return ScanResult(name, [e["name"] for e in entry["extracts"]])

    def add_back(
        self, scan: str, back: np.ndarray, dpi: int, *, calibration: str | None = None
    ) -> BackResult:
        """Pair a Scan of the flipped Prints with the fronts, read their text, re-date."""
        entry = self._scan(scan)
        entry["back_scan"] = f"{scan}_back"
        entry["back_calibration"] = calibration
        write_tiff(self.scan_file(entry["back_scan"]), back, self._meta(entry, dpi=dpi))
        result = self._backs(entry, back, dpi)
        self.save()
        return result

    def recut(self, scan: str) -> ScanResult:
        """Redo a Scan's Extracts (and Backs), with its own calibration and typed date."""
        entry = self._scan(scan)
        self._remove_outputs(scan, keep_scans=True)
        image, _ = read_tiff(self.scan_file(scan))
        entry["extracts"] = self._cut(image, entry)
        if entry.get("back_scan"):
            back, meta = read_tiff(self.scan_file(entry["back_scan"]))
            self._backs(entry, back, meta.dpi)
        entry["recut_at"] = _now()
        self.save()
        return ScanResult(scan, [e["name"] for e in entry["extracts"]])

    def discard(self, scan: str) -> None:
        """Throw a Scan away everywhere, e.g. when the preview shows a bad cut."""
        self._remove_outputs(scan, keep_scans=False)
        self._record["scans"] = [s for s in self.scans if s["scan"] != scan]
        self.save()

    def set_date(self, extract: str, typed: PhotoDate | None) -> None:
        """Type in (or, with None, clear) an Extract's Photo date; files are re-stamped."""
        scan, item = self._extract(extract)
        item["typed_date"] = str(typed) if typed else None
        self._stamp(scan, item)
        self.save()

    def set_estimate(self, estimate: PhotoDate | None) -> None:
        """Change the Source's estimate; Extracts that relied on it are re-stamped."""
        self._record["estimate"] = str(estimate) if estimate else None
        for scan in self.scans:
            for item in scan["extracts"]:
                if item["date_source"] in ("source", None):
                    self._stamp(scan, item)
        self.save()

    def save(self) -> None:
        scans = self.scans
        items = [e for s in scans for e in s["extracts"]]
        dated = sum(1 for e in items if e["date"])
        self._record["totals"] = {
            "scans": len(scans),
            "extracts": len(items),
            "dated": dated,
            "undated": len(items) - dated,
        }
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "source.json").write_text(
            json.dumps(self._record, ensure_ascii=False, indent=2)
        )

    # --- internals -------------------------------------------------------------

    def _cut(self, scan: np.ndarray, entry: dict) -> list[dict]:
        s = self.archive.settings
        calibration = self.archive.calibration(entry["calibration"])
        items = []
        regions = find_prints(
            scan, entry["dpi"], min_side_cm=s.min_side_cm, calibration=calibration
        )
        for i, region in enumerate(regions, start=1):
            image = cut(scan, region, inset_px=s.inset_px)
            dust = 0
            if calibration is not None:
                image, dust = repair_dust(image, calibration, region, inset_px=s.inset_px)
            item = {
                "name": f"{entry['scan']}_p{i:02d}",
                "region": [round(v, 2) for v in (*region.center, *region.size, region.angle)],
                "typed_date": entry["typed_date"],
                "date": None,
                "date_source": None,
                "text_front": self.archive.reader(image),
                "text_back": [],
                "back": None,
                "dust_repaired": dust,
            }
            self.master(item["name"]).parent.mkdir(parents=True, exist_ok=True)
            self.photo(item["name"]).parent.mkdir(parents=True, exist_ok=True)
            self._stamp(entry, item, image)
            items.append(item)
        return items

    def _backs(self, entry: dict, back: np.ndarray, dpi: int) -> BackResult:
        s = self.archive.settings
        for old in (self.path / "backs").glob(f"{entry['scan']}_*"):
            old.unlink()
        calibration = self.archive.calibration(entry.get("back_calibration"))
        found = find_prints(back, dpi, min_side_cm=s.min_side_cm, calibration=calibration)
        fronts = [_region(item["region"]) for item in entry["extracts"]]
        pairs, unmatched = match_backs(fronts, found, dpi)
        self.back("x").parent.mkdir(parents=True, exist_ok=True)
        meta = self._meta(entry, dpi=dpi)
        matched = {}
        for f, item in enumerate(entry["extracts"]):
            item["back"], item["text_back"] = None, []
            if f not in pairs:
                self._stamp(entry, item)
                continue
            image = cut(back, found[pairs[f]], inset_px=s.inset_px)
            item["back"] = f"{item['name']}_back"
            item["text_back"] = self.archive.reader(image)
            self._write_back(item["back"], image, meta)
            self._stamp(entry, item)
            matched[item["name"]] = item["back"]
        entry["unmatched_backs"] = []
        for n, b in enumerate(unmatched, start=1):
            name = f"{entry['scan']}_back_unmatched_{n:02d}"
            self._write_back(name, cut(back, found[b], inset_px=s.inset_px), meta)
            entry["unmatched_backs"].append(name)
        return BackResult(matched, entry["unmatched_backs"])

    def _write_back(self, name: str, image: np.ndarray, meta: Meta) -> None:
        write_tiff(self.back(name), image, meta)
        write_jpeg(self.back(name, ".jpg"), image, meta, quality=self.archive.settings.jpeg_quality)

    def _stamp(self, entry: dict, item: dict, image: np.ndarray | None = None) -> None:
        """Resolve the Extract's Photo date and (re)write its master and photo."""
        typed = PhotoDate.parse(item["typed_date"]) if item["typed_date"] else None
        date_, source = choose_date(typed, item["text_back"], item["text_front"], self.estimate)
        item["date"], item["date_source"] = (str(date_) if date_ else None), source
        if image is None:
            image, _ = read_tiff(self.master(item["name"]))
        meta = self._meta(entry, photo_date=date_, date_source=source)
        write_tiff(self.master(item["name"]), image, meta)
        quality = self.archive.settings.jpeg_quality
        write_jpeg(self.photo(item["name"]), image, meta, quality=quality)

    def _meta(self, entry: dict, *, dpi: int | None = None, **dated) -> Meta:
        scanned = datetime.fromisoformat(entry["scanned_at"])
        return Meta(self.name, scanned, dpi or entry["dpi"], **dated)

    def _remove_outputs(self, scan: str, *, keep_scans: bool) -> None:
        doomed = [
            *(self.path / "masters").glob(f"{scan}_p*"),
            *(self.archive.photos / self.slug).glob(f"{scan}_p*"),
            *(self.path / "backs").glob(f"{scan}_*"),
        ]
        if not keep_scans:
            doomed += [self.scan_file(scan), self.scan_file(f"{scan}_back")]
        for path in doomed:
            path.unlink(missing_ok=True)

    def _scan(self, scan: str) -> dict:
        for entry in self.scans:
            if entry["scan"] == scan:
                return entry
        raise KeyError(f"no Scan {scan!r} in Source {self.name!r}")

    def _extract(self, extract: str) -> tuple[dict, dict]:
        for entry in self.scans:
            for item in entry["extracts"]:
                if item["name"] == extract:
                    return entry, item
        raise KeyError(f"no Extract {extract!r} in Source {self.name!r}")

    def _next_number(self) -> int:
        names = [s["scan"] for s in self.scans]
        names += [p.stem for p in (self.path / "scans").glob("*.tif")]
        numbers = [int(m[1]) for n in names if (m := re.search(r"_s(\d{3,})$", n))]
        return max(numbers, default=0) + 1


def _region(values: list[float]) -> Region:
    cx, cy, w, h, angle = values
    return Region(center=(cx, cy), size=(w, h), angle=angle)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "untitled"
