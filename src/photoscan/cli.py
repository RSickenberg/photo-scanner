"""`photoscan`: the command line."""

import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
import typer

from photoscan import backup, config, scanners
from photoscan.archive import Archive, ScanResult, Session, Source
from photoscan.dates import PhotoDate
from photoscan.detect import Region
from photoscan.imagefiles import to_8bit
from photoscan.scanners import Scanner, ScannerError

app = typer.Typer(
    no_args_is_help=True,
    help="Scan several family photos at once and cut each one into its own file.",
)

DATE_HELP = "1985-06-15, 1985-06, 1985, 1980s, ~1985 (approximate)"
_PREVIEW_LONG_SIDE = 1200  # px: plenty to check the cuts, quick to open


def make_scanner(cfg: config.Config) -> Scanner:
    return scanners.create(cfg.backend, cfg.device)


def make_archive(cfg: config.Config) -> Archive:
    return Archive(cfg.output_dir, settings=cfg.cut)


@app.command()
def session(
    source: Annotated[
        str | None, typer.Argument(help='Source to start with, e.g. "Album Grand-mère"')
    ] = None,
    dpi: Annotated[int | None, typer.Option(help="Overrides the config (default 600)")] = None,
    deep: Annotated[bool, typer.Option("--16bit", help="16 bits per channel")] = False,
    preview: Annotated[bool, typer.Option(help="Check the cuts after each Scan")] = False,
    calibrate: Annotated[
        bool, typer.Option(help="Scan the empty glass first (background + dust)")
    ] = True,
) -> None:
    """Scan batch after batch of Prints, filing each Scan under a Source."""
    cfg = _config()
    dpi = dpi or cfg.dpi
    archive = make_archive(cfg)
    current = _pick_source(archive, source)
    sitting = archive.start_session()
    scanner = make_scanner(cfg)
    syncer = _start_backup(cfg)
    typed: PhotoDate | None = None
    last: tuple[Source, str] | None = None  # the Scan a Back pass applies to
    total = 0

    def backup_now() -> None:
        if syncer:
            syncer.request()

    try:
        if calibrate and not _reuse_calibration(archive, sitting, scanner, dpi, cfg):
            _calibrate(sitting, scanner, dpi, deep)
        while True:
            when = (
                str(typed)
                if typed
                else (f"est. {current.estimate}" if current.estimate else "date unknown")
            )
            answer = (
                typer.prompt(
                    f"[{current.name} · {when}] Enter scan · b backs · d date · o source"
                    " · c calibrate · q finish",
                    default="",
                    show_default=False,
                )
                .strip()
                .lower()
            )
            if answer == "q":
                break
            if answer == "c":
                _calibrate(sitting, scanner, dpi, deep)
            elif answer == "o":
                current, typed, last = _pick_source(archive, None), None, None
            elif answer == "d":
                typed = _ask_date(
                    "Photo date for the next Scans (empty = back to the Source's estimate)"
                )
            elif answer == "b":
                if last is None:
                    typer.echo("Scan the fronts first; b then scans their Backs.")
                elif _scan_backs(sitting, *last, scanner, cfg.back_dpi):
                    backup_now()
            elif answer == "" and (
                scanned := _scan_fronts(sitting, current, scanner, dpi, deep, typed, preview)
            ):
                last = (current, scanned.scan)
                total += len(scanned.extracts)
                backup_now()
    finally:
        if syncer:
            typer.echo("Finishing the Backup to the NAS…")
            syncer.close()
    typer.echo(f"Done: {total} Extract(s). Photos in {archive.photos}")


@app.command()
def recut(
    scans: Annotated[list[Path], typer.Argument(help="Scan TIFFs (archive/*/scans)")],
) -> None:
    """Redo the Extracts (and Backs) of existing Scans."""
    archive = make_archive(_config())
    for path in scans:
        source, name = archive.locate(path)
        result = source.recut(name)
        typer.echo(f"{name}: {len(result.extracts)} Extract(s)")
        if source.entry(name).get("calibration_missing"):
            typer.secho(
                "  its calibration was pruned: cut without it (no dust repair)", fg="yellow"
            )


@app.command()
def rotate(
    extracts: Annotated[list[Path], typer.Argument(help="Photos (.jpg) or masters (.tif)")],
    degrees: Annotated[int, typer.Option(help="Clockwise: 90, 180 or 270")] = 90,
) -> None:
    """Turn Extracts that came out sideways or upside down (master and photo together)."""
    archive = make_archive(_config())
    for extract in extracts:
        archive.rotate(extract, degrees)
        typer.echo(f"rotated {extract.stem} by {degrees}°")


@app.command(name="date")
def set_date(
    value: Annotated[str, typer.Argument(help=f"{DATE_HELP}; empty to clear")],
    extracts: Annotated[
        list[Path] | None, typer.Argument(help="Photos (.jpg) or masters (.tif)")
    ] = None,
    source: Annotated[str | None, typer.Option(help="Set this Source's estimate instead")] = None,
) -> None:
    """Set the Photo date of Extracts, or a Source's estimate, and re-stamp the files."""
    try:
        when = PhotoDate.parse(value)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    archive = make_archive(_config())
    if source:
        _existing_source(archive, source).set_estimate(when)
        typer.echo(f"{source}: estimate {when or 'unknown'}")
    for path in extracts or []:
        found, name = archive.locate(path)
        found.set_date(name, when)
        typer.echo(f"{name}: {when or 'typed date cleared'}")


@app.command()
def dates(source: Annotated[str | None, typer.Argument(help="Only this Source")] = None) -> None:
    """List every Extract with its Photo date and where the date came from."""
    archive = make_archive(_config())
    chosen = [_existing_source(archive, source)] if source else archive.sources()
    for src in chosen:
        estimate = f" (estimate {src.estimate})" if src.estimate else ""
        typer.secho(f"{src.name}{estimate}", bold=True)
        for scan in src.scans:
            for item in scan["extracts"]:
                where = item["date_source"] or "-"
                typer.echo(f"  {item['name']:<32} {item['date'] or 'unknown':<14} {where}")


@app.command()
def sync() -> None:
    """Copy everything not yet on the NAS, verifying each file."""
    cfg = _require_nas(_config())
    report = backup.sync(cfg.output_dir, cfg.nas_dir)
    typer.echo(f"{len(report.copied)} file(s) copied, {len(report.failed)} failed")
    if report.failed:
        raise typer.Exit(1)


@app.command()
def prune(
    yes: Annotated[bool, typer.Option("--yes", help="Don't ask")] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Skip the NAS: delete ALL local files, even those never backed up",
        ),
    ] = False,
) -> None:
    """Delete local files whose NAS copy is verified identical."""
    if force:
        cfg = _config()
        if not yes:
            lost = backup.not_backed_up(cfg.output_dir)
            typer.secho(
                f"{len(lost)} local file(s) are NOT on the NAS and will be lost for good.",
                fg="red" if lost else None,
            )
            typer.confirm(f"Delete ALL Scans and Extracts in {cfg.output_dir}?", abort=True)
        deleted = backup.delete_all(cfg.output_dir)
        typer.echo(f"{len(deleted)} local file(s) deleted")
        return
    cfg = _require_nas(_config())
    if not yes:
        typer.confirm(f"Delete backed-up files from {cfg.output_dir}?", abort=True)
    deleted = backup.prune(cfg.output_dir, cfg.nas_dir)
    typer.echo(f"{len(deleted)} local file(s) deleted")


@app.command()
def devices() -> None:
    """List the scanners the configured backend can see."""
    cfg = _config()
    found = make_scanner(cfg).devices()
    typer.echo("\n".join(found) if found else "No scanner found. Is it plugged in and on?")


@app.command(name="config")
def show_config() -> None:
    """Show the config file, creating a commented example if there is none."""
    path = config.config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(config.EXAMPLE)
        typer.echo(f"Created {path}; set nas_dir in it.")
    typer.echo(f"{path}\n\n{path.read_text()}")


def _config() -> config.Config:
    try:
        return config.load()
    except config.ConfigError as error:
        typer.secho(f"{config.config_path()}: {error}", fg="red", err=True)
        raise typer.Exit(1) from error


def _existing_source(archive: Archive, name: str) -> Source:
    """A Source to look at or change: never created by a typo."""
    if found := archive.find_source(name):
        return found
    known = ", ".join(repr(s.name) for s in archive.sources()) or "none yet"
    typer.secho(f"No Source named {name!r}. Known: {known}", fg="red", err=True)
    raise typer.Exit(1)


def _calibrate(sitting: Session, scanner: Scanner, dpi: int, deep: bool) -> None:
    """Scan the empty glass; retried until it works or is skipped."""
    while True:
        answer = typer.prompt(
            "Calibration: empty the glass, close the lid (or lay the cloth), then Enter"
            " (s to skip)",
            default="",
            show_default=False,
        )
        if answer.strip().lower() == "s":
            typer.echo("Not calibrated: the background is estimated from each Scan's border.")
            return
        image = _scan(scanner, dpi, deep)
        if image is None:
            continue
        cal = sitting.calibrate(image, dpi, scanner=scanner.name)
        typer.echo(f"Calibrated: noise {cal.noise:.1f}, {cal.dust_specks} speck(s) seen")
        return


def _reuse_calibration(
    archive: Archive, sitting: Session, scanner: Scanner, dpi: int, cfg: config.Config
) -> bool:
    """Reuse a calibration made recently on this scanner and dpi, if any."""
    max_age = timedelta(minutes=cfg.calibration_max_age_minutes)
    recent = archive.recent_calibration(scanner.name, dpi, max_age)
    if recent is None:
        return False
    cal_id, made = recent
    sitting.use_calibration(cal_id)
    minutes = round((datetime.now() - made).total_seconds() / 60)
    typer.echo(f"Using the calibration from {minutes} min ago (press c to redo it).")
    return True


def _scan_fronts(
    sitting: Session,
    source: Source,
    scanner: Scanner,
    dpi: int,
    deep: bool,
    typed: PhotoDate | None,
    preview: bool,
) -> ScanResult | None:
    """Scan the Prints on the glass into `source`; None if it failed or was discarded."""
    image = _scan(scanner, dpi, deep)
    if image is None:
        return None
    result = sitting.add_scan(source, image, dpi, scanner=scanner.name, typed=typed)
    typer.echo(f"{result.scan}: {len(result.extracts)} Extract(s)")
    if preview and _rejected_after_preview(image, source, result.scan):
        source.discard(result.scan)
        typer.echo("Discarded; rearrange the Prints and scan again.")
        return None
    return result


def _scan_backs(sitting: Session, source: Source, scan: str, scanner: Scanner, dpi: int) -> bool:
    """Scan the flipped Prints of `scan` and pair their Backs; False if the scan failed."""
    flip = "Flip every Print in place (same spot), then Enter"
    typer.prompt(flip, default="", show_default=False)
    image = _scan(scanner, dpi, False)
    if image is None:
        return False
    result = sitting.add_back(source, scan, image, dpi)
    typer.echo(f"{len(result.matched)} Back(s) matched to their fronts")
    for name in result.unmatched:
        typer.secho(f"Unmatched Back kept as {name}", fg="yellow")
    return True


def _scan(scanner: Scanner, dpi: int, deep: bool) -> np.ndarray | None:
    try:
        return scanner.scan(dpi, deep=deep)
    except ScannerError as error:
        typer.secho(f"Scan failed: {error}", fg="red", err=True)
        return None


def _pick_source(archive: Archive, name: str | None) -> Source:
    """An existing Source by number or name, or a new one (asking its rough date)."""
    existing = archive.sources()
    if name is None:
        for i, src in enumerate(existing, start=1):
            estimate = f" · est. {src.estimate}" if src.estimate else ""
            typer.echo(f"  {i}. {src.name}{estimate}")
        name = typer.prompt("Source (number, or a new name)").strip()
        if name.isdigit() and 1 <= int(name) <= len(existing):
            return existing[int(name) - 1]
    for src in existing:
        if src.name == name:
            return src
    estimate = _ask_date(f"Rough date for {name!r} ({DATE_HELP}; empty = unknown)")
    return archive.source(name, estimate=estimate)


def _ask_date(question: str) -> PhotoDate | None:
    while True:
        try:
            return PhotoDate.parse(typer.prompt(question, default="", show_default=False))
        except ValueError as error:
            typer.secho(str(error), fg="red")


def _start_backup(cfg: config.Config) -> backup.BackgroundSync | None:
    if not cfg.nas_dir:
        typer.echo("No nas_dir configured: files stay local (see `photoscan config`).")
        return None
    warned = False

    def report(result) -> None:
        nonlocal warned
        if isinstance(result, backup.NasUnavailable):
            if not warned:
                typer.secho(f"\n{result}. Keep scanning; run `photoscan sync` later.", fg="yellow")
                warned = True
        elif isinstance(result, Exception):
            typer.secho(f"\nBackup error: {result}", fg="red")
        elif result.failed:
            typer.secho(f"\n{len(result.failed)} file(s) failed to reach the NAS", fg="red")

    return backup.BackgroundSync(cfg.output_dir, cfg.nas_dir, report)


def _require_nas(cfg: config.Config) -> config.Config:
    if not cfg.nas_dir:
        typer.secho("Set nas_dir in the config first (`photoscan config`).", fg="red", err=True)
        raise typer.Exit(1)
    return cfg


def _rejected_after_preview(image: np.ndarray, source: Source, scan: str) -> bool:
    """Open the Scan in Preview.app with the cuts just made, numbered; ask to keep it."""
    scale = _PREVIEW_LONG_SIDE / max(image.shape[:2])
    small = cv2.resize(to_8bit(image), None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    for i, item in enumerate(source.entry(scan)["extracts"], start=1):
        box = Region.from_list(item["region"]).scaled(scale).box().astype(np.int32)
        cv2.polylines(small, [box], True, (255, 40, 40), 3)
        label_at = tuple(box.mean(axis=0).astype(int))
        cv2.putText(small, str(i), label_at, cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 40, 40), 4)
    path = Path(tempfile.gettempdir()) / "photoscan-preview.jpg"
    cv2.imwrite(str(path), cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
    subprocess.run(["open", str(path)], check=False)
    answer = typer.prompt("Enter to keep, r to discard and rescan", default="", show_default=False)
    return answer.strip().lower() == "r"
