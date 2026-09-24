"""`photoscan`: the command line."""

import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
import typer

from photoscan import backup, config, scanners
from photoscan.detect import find_prints
from photoscan.scanners import Scanner, ScannerError
from photoscan.session import Session, rotate_extract

app = typer.Typer(
    no_args_is_help=True,
    help="Scan several family photos at once and cut each one into its own file.",
)


def make_scanner(cfg: config.Config) -> Scanner:
    return scanners.create(cfg.backend, cfg.device)


@app.command()
def session(
    label: Annotated[str | None, typer.Argument(help='e.g. "Grandma album 1970s"')] = None,
    dpi: Annotated[int | None, typer.Option(help="Overrides the config (default 600)")] = None,
    deep: Annotated[bool, typer.Option("--16bit", help="16 bits per channel")] = False,
    preview: Annotated[bool, typer.Option(help="Check the cuts after each Scan")] = False,
    calibrate: Annotated[
        bool, typer.Option(help="Scan the empty glass first (background + dust)")
    ] = True,
) -> None:
    """Scan batch after batch of Prints, cutting each Scan into Extracts."""
    cfg = config.load()
    label = label or typer.prompt("Label for this Session")
    dpi = dpi or cfg.dpi
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    day = date.today()
    known = backup.known_names(cfg.output_dir, Session.folder(cfg.output_dir, label, day))
    s = Session.open(cfg.output_dir, label, day, settings=cfg.cut, known=known)
    scanner = make_scanner(cfg)
    syncer = _start_backup(cfg)
    typer.echo(f"Session: {s.path}")

    total = 0
    try:
        if calibrate:
            _calibrate(s, scanner, dpi, deep)
        while True:
            answer = (
                typer.prompt(
                    "Place Prints, then Enter to scan (c to recalibrate, q to finish)",
                    default="",
                    show_default=False,
                )
                .strip()
                .lower()
            )
            if answer == "q":
                break
            if answer == "c":
                _calibrate(s, scanner, dpi, deep)
                continue
            try:
                image = scanner.scan(dpi, deep=deep)
            except ScannerError as error:
                typer.secho(f"Scan failed: {error}", fg="red", err=True)
                continue
            result = s.add_scan(image, dpi, scanner=scanner.name)
            typer.echo(f"{result.scan.name}: {len(result.extracts)} Extract(s)")
            if preview and _rejected_after_preview(image, dpi, s):
                s.discard(result.scan)
                typer.echo("Discarded; rearrange the Prints and scan again.")
                continue
            total += len(result.extracts)
            if syncer:
                syncer.request()
    finally:
        if syncer:
            typer.echo("Finishing the Backup to the NAS…")
            syncer.close()
    typer.echo(f"Done: {total} Extract(s) in {s.path}")


@app.command()
def recut(scans: Annotated[list[Path], typer.Argument(help="Scan TIFFs (scans/*.tif)")]) -> None:
    """Redo the Extracts of existing Scans."""
    cfg = config.load()
    for scan in scans:
        extracts = Session.load(scan.resolve().parents[1], settings=cfg.cut).recut(scan)
        typer.echo(f"{scan.name}: {len(extracts)} Extract(s)")


@app.command()
def rotate(
    extracts: Annotated[list[Path], typer.Argument(help="Extract files (.tif or .jpg)")],
    degrees: Annotated[int, typer.Option(help="Clockwise: 90, 180 or 270")] = 90,
) -> None:
    """Turn Extracts that came out sideways or upside down (TIFF and JPEG together)."""
    cfg = config.load()
    for extract in extracts:
        rotate_extract(extract, degrees, jpeg_quality=cfg.cut.jpeg_quality)
        typer.echo(f"rotated {extract.stem} by {degrees}°")


@app.command()
def sync() -> None:
    """Copy everything not yet on the NAS, verifying each file."""
    cfg = _require_nas(config.load())
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
        cfg = config.load()
        if not yes:
            lost = backup.not_backed_up(cfg.output_dir)
            typer.secho(
                f"{len(lost)} local file(s) are NOT on the NAS and will be lost for good.",
                fg="red" if lost else None,
            )
            typer.confirm(f"Delete ALL Scans and Extracts in {cfg.output_dir}?", abort=True)
        deleted = backup.prune(cfg.output_dir, None, force=True)
        typer.echo(f"{len(deleted)} local file(s) deleted")
        return
    cfg = _require_nas(config.load())
    if not yes:
        typer.confirm(f"Delete backed-up files from {cfg.output_dir}?", abort=True)
    deleted = backup.prune(cfg.output_dir, cfg.nas_dir)
    typer.echo(f"{len(deleted)} local file(s) deleted")


@app.command()
def devices() -> None:
    """List the scanners the configured backend can see."""
    cfg = config.load()
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


def _calibrate(s: Session, scanner: Scanner, dpi: int, deep: bool) -> None:
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
        try:
            cal = s.calibrate(scanner.scan(dpi, deep=deep), dpi, scanner=scanner.name)
        except ScannerError as error:
            typer.secho(f"Calibration scan failed: {error}", fg="red", err=True)
            continue
        typer.echo(f"Calibrated: noise {cal.noise:.1f}, {cal.dust_specks} dust speck(s) on glass")
        if cal.dust_specks > 50:
            typer.secho("That's a lot of dust: clean the glass, then press c.", fg="yellow")
        return


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


def _rejected_after_preview(image: np.ndarray, dpi: int, s: Session) -> bool:
    """Open the Scan with numbered boxes in Preview.app; ask whether to keep it."""
    small = (image >> 8).astype(np.uint8) if image.dtype == np.uint16 else image
    scale = 1200 / max(small.shape[:2])
    small = np.ascontiguousarray(cv2.resize(small, None, fx=scale, fy=scale))
    regions = find_prints(image, dpi, min_side_cm=s.settings.min_side_cm, calibration=s.calibration)
    for i, r in enumerate(regions, start=1):
        rect = ((r.center[0] * scale, r.center[1] * scale),
                (r.size[0] * scale, r.size[1] * scale), r.angle)  # fmt: skip
        box = cv2.boxPoints(rect).astype(np.int32)
        cv2.polylines(small, [box], True, (255, 40, 40), 3)
        cv2.putText(small, str(i), tuple(box.mean(axis=0).astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 40, 40), 4)  # fmt: skip
    path = Path(tempfile.gettempdir()) / "photoscan-preview.jpg"
    cv2.imwrite(str(path), cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
    subprocess.run(["open", str(path)], check=False)
    answer = typer.prompt("Enter to keep, r to discard and rescan", default="", show_default=False)
    return answer.strip().lower() == "r"
