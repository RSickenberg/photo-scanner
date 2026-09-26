"""The archive on disk, organised by Source (ADR 0002).

    <root>/photos/<source>/<source>_s001_p01.jpg     fronts only: point Ugreen Photos here
    <root>/archive/<source>/source.json               the Source's record (never pruned)
    <root>/archive/<source>/scans/<source>_s001.tif   whole Scans (+ _back.jpg)
    <root>/archive/<source>/masters/<source>_s001_p01.tif   lossless Extracts
    <root>/archive/<source>/backs/<source>_s001_p01_back.jpg
    <root>/archive/_sessions/<date>_01.json           each sitting: calibrations, Scans made
    <root>/archive/_calibrations/<date>_01_cal_01.tif  empty-glass Scans

The Photo date lives in each Extract's metadata, never in names, so it can be
corrected without renaming (and re-uploading) anything.
"""

import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from photoscan import detect
from photoscan.dates import PhotoDate, choose_date
from photoscan.detect import (
    BACK_TOLERANCE_CM,
    Calibration,
    Region,
    cut,
    distance_outside,
    enclose,
    find_prints,
    match_backs,
    repair_dust,
    same_picture,
)
from photoscan.imagefiles import (
    Meta,
    is_compact,
    read_jpeg,
    read_tiff,
    read_tiff_pages,
    replace_tiff,
    write_jpeg,
    write_tiff,
)

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
    not_flipped: list[str]  # Extracts still face up on the Back Scan
    missing: list[str]  # Extracts with nothing where they lay: removed (or a blank Back)


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

    def find_source(self, name: str) -> "Source | None":
        """An existing Source by name; None if there's none (nothing is created)."""
        path = self.archive / slugify(name) / "source.json"
        return Source(self, json.loads(path.read_text())) if path.exists() else None

    def source(self, name: str, *, estimate: PhotoDate | None = None) -> "Source":
        """Open a Source, creating it (with its date estimate) if it's new."""
        if found := self.find_source(name):
            return found
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

    def add_calibration(self, cal_id: str, empty: np.ndarray, dpi: int) -> Calibration:
        """Keep an empty-glass Scan under `cal_id` and learn from it."""
        folder = self.archive / "_calibrations"
        folder.mkdir(parents=True, exist_ok=True)
        grey, small = detect.glass_parts(empty)
        write_tiff(folder / f"{cal_id}.tif", grey, Meta("Calibration", datetime.now(), dpi), small)
        self._calibrations[cal_id] = detect.calibrate_from(grey, small, dpi)
        return self._calibrations[cal_id]

    def calibration(self, cal_id: str | None) -> Calibration | None:
        """A calibration by id; None if there's none, or its empty-glass Scan was pruned."""
        if cal_id is None:
            return None
        if cal_id not in self._calibrations:
            path = self.archive / "_calibrations" / f"{cal_id}.tif"
            if not path.exists():
                return None
            pages, meta = read_tiff_pages(path)
            if len(pages) == 1:  # the whole empty-glass Scan, as kept before 2.3
                pages = detect.glass_parts(pages[0])
            self._calibrations[cal_id] = detect.calibrate_from(*pages, meta.dpi)
        return self._calibrations[cal_id]

    def recent_calibration(
        self, scanner: str | None, dpi: int, max_age: timedelta, *, now: datetime | None = None
    ) -> tuple[str, datetime] | None:
        """The latest calibration (id, time) made on this scanner at this dpi within
        `max_age`, if its empty-glass Scan is still on disk (it may have been pruned)."""
        now = now or datetime.now()
        usable = [
            (cal["id"], datetime.fromisoformat(cal["calibrated_at"]))
            for record in (self.archive / "_sessions").glob("*.json")
            for cal in json.loads(record.read_text()).get("calibrations", [])
            if not cal.get("reused")
            and cal["scanner"] == scanner
            and cal["dpi"] == dpi
            and (self.archive / "_calibrations" / f"{cal['id']}.tif").exists()
        ]
        recent = [(cal_id, made) for cal_id, made in usable if now - made <= max_age]
        return max(recent, key=lambda c: c[1], default=None)

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
        calibration = self.archive.add_calibration(cal_id, empty, dpi)
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

    def use_calibration(self, cal_id: str) -> Calibration:
        """Reuse an earlier Session's calibration instead of scanning the empty glass again."""
        calibration = self.archive.calibration(cal_id)
        self._record["calibrations"].append({"id": cal_id, "reused": True})
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

    def back_scan_file(self, scan: str) -> Path:
        """The whole Back Scan: a JPEG, being kept only for what's printed on it.
        (Before 2.0.3 it was a TIFF, which is still read.)"""
        jpeg = self.path / "scans" / f"{scan}_back.jpg"
        tiff = self.path / "scans" / f"{scan}_back.tif"
        return tiff if tiff.exists() and not jpeg.exists() else jpeg

    def master(self, extract: str) -> Path:
        return self.path / "masters" / f"{extract}.tif"

    def photo(self, extract: str) -> Path:
        return self.archive.photos / self.slug / f"{extract}.jpg"

    def back(self, name: str) -> Path:
        return self.path / "backs" / f"{name}.jpg"

    def _make_folders(self) -> None:
        for folder in ("scans", "masters", "backs"):
            (self.path / folder).mkdir(parents=True, exist_ok=True)
        (self.archive.photos / self.slug).mkdir(parents=True, exist_ok=True)

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
        self._make_folders()
        write_tiff(self.scan_file(name), scan, self._meta(entry))
        entry["extracts"] = self._cut(scan, entry)
        self.scans.append(entry)
        self.save()
        return ScanResult(name, [e["name"] for e in entry["extracts"]])

    def add_back(
        self, scan: str, back: np.ndarray, dpi: int, *, calibration: str | None = None
    ) -> BackResult:
        """Pair a Scan of the flipped Prints with the fronts, read their text, re-date."""
        entry = self.entry(scan)
        self._make_folders()
        entry["back_scan"] = f"{scan}_back"
        entry["back_calibration"] = calibration
        entry["back_dpi"] = dpi  # may be lower than the front's: only text is needed
        quality = self.archive.settings.jpeg_quality
        write_jpeg(self.back_scan_file(scan), back, self._meta(entry, dpi=dpi), quality=quality)
        result = self._backs(entry, back, dpi)
        self.save()
        return result

    def recut(self, scan: str) -> ScanResult:
        """Redo a Scan's Extracts (and Backs), with its own calibration and typed date."""
        entry = self.entry(scan)
        self._make_folders()
        self._remove_outputs(scan, keep_scans=True)
        image, _ = read_tiff(self.scan_file(scan))
        entry["extracts"] = self._cut(image, entry)
        if entry.get("back_scan"):
            path = self.back_scan_file(scan)
            back = read_tiff(path)[0] if path.suffix == ".tif" else read_jpeg(path)
            self._backs(entry, back, entry.get("back_dpi") or entry["dpi"])
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

    def latest_scan(self) -> str | None:
        """The Source's most recent Scan, from any Session."""
        return self.scans[-1]["scan"] if self.scans else None

    def set_scan_date(self, scan: str, when: PhotoDate | None) -> list[str]:
        """Date all of a Scan's Extracts at once (None clears it), except those
        dated by hand or by their Back, which are kept. Returns the kept ones."""
        entry = self.entry(scan)
        entry["scan_date"] = str(when) if when else None
        for item in entry["extracts"]:
            self._stamp(entry, item)
        self.save()
        trusted = ("typed", "ocr-back")
        return [i["name"] for i in entry["extracts"] if when and i["date_source"] in trusted]

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
        # Pruned calibration: fall back to uncalibrated detection, and say so.
        entry["calibration_missing"] = bool(entry["calibration"]) and calibration is None
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
                "region": region.as_list(),
                "typed_date": entry["typed_date"],
                "date": None,
                "date_source": None,
                "text_front": self.archive.reader(image),
                "text_back": [],
                "back": None,
                "dust_repaired": dust,
            }
            self._stamp(entry, item, image)
            items.append(item)
        return items

    def _backs(self, entry: dict, back: np.ndarray, dpi: int) -> BackResult:
        s = self.archive.settings
        for old in (self.path / "backs").glob(f"{entry['scan']}_*"):
            old.unlink()
        calibration = self.archive.calibration(entry.get("back_calibration"))
        found = find_prints(back, dpi, min_side_cm=s.min_side_cm, calibration=calibration)
        # Fronts' regions are in the front Scan's pixels; bring them to the Back's.
        scale = dpi / entry["dpi"]
        fronts = [Region.from_list(item["region"]).scaled(scale) for item in entry["extracts"]]
        pairs, unmatched = match_backs(fronts, found, dpi)
        # A pale Back on a pale lid can come out as several pieces, none the size
        # of its front (real white Kodak back, 2026-09-24). Pieces lying where an
        # unpaired front was are its Back; it's cut from the front's footprint
        # plus those pieces, so nothing is lost if the Print moved a little. A
        # Back that wasn't detected at all is still cut from the footprint: its
        # faint printing may be readable even if it wasn't seen as a Print.
        tolerance = BACK_TOLERANCE_CM / 2.54 * dpi
        pieces: dict[int, list[int]] = {f: [] for f in range(len(fronts)) if f not in pairs}
        for b in list(unmatched):
            gaps = {f: distance_outside(fronts[f], found[b].center) for f in pieces}
            if gaps and min(gaps.values()) <= tolerance:
                pieces[min(gaps, key=gaps.get)].append(b)
                unmatched.remove(b)
        meta = self._meta(entry, dpi=dpi)
        matched, not_flipped, missing = {}, [], []
        for f, item in enumerate(entry["extracts"]):
            if f in pairs:
                where = found[pairs[f]]
            else:
                where = enclose([fronts[f], *(found[b] for b in pieces[f])])
            image = cut(back, where, inset_px=s.inset_px)
            # Not every Print has to be flipped: one still face up isn't a Back...
            unflipped = same_picture(image, read_tiff(self.master(item["name"]))[0])
            text = [] if unflipped else self.archive.reader(image)
            # ...and one taken off the glass leaves only lid where it lay. Nothing
            # detected there is kept only for text read on it (a faint Back).
            footprint_only = f not in pairs and not pieces[f]
            if unflipped or (footprint_only and not text):
                item["back"], item["text_back"] = None, []
                self._stamp(entry, item)
                (not_flipped if unflipped else missing).append(item["name"])
                continue
            item["back"] = f"{item['name']}_back"
            item["text_back"] = text
            self._write_back(item["back"], image, meta)
            self._stamp(entry, item)
            matched[item["name"]] = item["back"]
        entry["unmatched_backs"] = []
        for n, b in enumerate(unmatched, start=1):
            name = f"{entry['scan']}_back_unmatched_{n:02d}"
            self._write_back(name, cut(back, found[b], inset_px=s.inset_px), meta)
            entry["unmatched_backs"].append(name)
        return BackResult(matched, entry["unmatched_backs"], not_flipped, missing)

    def _write_back(self, name: str, image: np.ndarray, meta: Meta) -> None:
        # Backs are kept for what's printed on them: a JPEG is enough.
        write_jpeg(self.back(name), image, meta, quality=self.archive.settings.jpeg_quality)

    def _stamp(self, entry: dict, item: dict, image: np.ndarray | None = None) -> None:
        """Resolve the Extract's Photo date and (re)write its master and photo."""
        typed = PhotoDate.parse(item["typed_date"]) if item["typed_date"] else None
        scan_date = PhotoDate.parse(entry["scan_date"]) if entry.get("scan_date") else None
        date_, source = choose_date(
            typed, item["text_back"], item["text_front"], self.estimate, scan_date=scan_date
        )
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
            doomed += [self.scan_file(scan), *(self.path / "scans").glob(f"{scan}_back.*")]
        for path in doomed:
            path.unlink(missing_ok=True)

    def entry(self, scan: str) -> dict:
        """The record of one Scan."""
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


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "untitled"


@dataclass
class CompactReport:
    rewritten: list[Path] = field(default_factory=list)
    bytes_before: int = 0
    bytes_after: int = 0


def compact(
    root: Path,
    *,
    only: Callable[[Path], bool] = lambda path: True,
    progress: Callable[[list[Path]], Iterable[Path]] = lambda files: files,
) -> CompactReport:
    """Rewrite the TIFFs of earlier versions under `root` (a local folder or the
    NAS) in today's smaller forms: the predictor on every TIFF, calibrations as
    their `glass_parts`. Lossless: each file is replaced only once the new one
    reads back identical. `only` picks the files; `progress` wraps them."""
    archive = root / "archive"
    calibrations = sorted((archive / "_calibrations").glob("*.tif"))
    images = sorted(archive.glob("[!_]*/scans/*.tif")) + sorted(archive.glob("[!_]*/masters/*.tif"))
    todo = [p for p in calibrations if only(p) and not is_compact(p, pages=2)]
    todo += [p for p in images if only(p) and not is_compact(p, pages=1)]
    report = CompactReport()
    for path in progress(todo):
        report.bytes_before += path.stat().st_size
        pages, meta = read_tiff_pages(path)
        if path.parent.name == "_calibrations" and len(pages) == 1:
            pages = list(detect.glass_parts(pages[0]))
        replace_tiff(path, pages, meta)
        report.bytes_after += path.stat().st_size
        report.rewritten.append(path)
    return report
