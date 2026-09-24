"""Backup of the local output folder to the NAS: copy, verify, and only then trust.

Scanning always writes locally first (see DECISIONS.md); this module mirrors
that tree onto the mounted NAS share. A manifest at the local root records the
SHA-256 of every file confirmed on the NAS, so later syncs skip unchanged
files and `prune` knows what is safe to delete locally.
"""

import hashlib
import json
import queue
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST = ".backup.json"
# Records (source.json, sessions) stay local even when backed up: tiny, and
# they keep numbering and history going after the images are pruned.
_KEEP_SUFFIX = ".json"


class NasUnavailable(Exception):
    pass


@dataclass
class SyncReport:
    copied: list[Path] = field(default_factory=list)
    failed: list[Path] = field(default_factory=list)


def sync(local: Path, nas: Path) -> SyncReport:
    """Copy every new or changed local file to the NAS, verifying each copy."""
    _require_mounted(nas)
    manifest = _load(local)
    report = SyncReport()
    for path in _local_files(local):
        rel = path.relative_to(local).as_posix()
        digest = _sha256(path)
        if manifest.get(rel) == digest:
            continue
        if _copy_verified(path, nas / rel, digest):
            manifest[rel] = digest
            _save(local, manifest)  # after each file: an interrupted sync keeps its progress
            report.copied.append(path)
        else:
            report.failed.append(path)
    return report


def prune(local: Path, nas: Path) -> list[Path]:
    """Delete local files whose NAS copy is re-verified identical right now.
    Records (*.json) are always kept."""
    _require_mounted(nas)
    manifest = _load(local)
    deleted = []
    for path in _local_files(local):
        rel = path.relative_to(local).as_posix()
        if path.suffix == _KEEP_SUFFIX or rel not in manifest:
            continue
        remote = nas / rel
        if _sha256(path) == manifest[rel] and remote.exists() and _sha256(remote) == manifest[rel]:
            path.unlink()
            deleted.append(path)
    return deleted


def delete_all(local: Path) -> list[Path]:
    """Delete every local image, backed up or not, without looking at the NAS
    (`prune --force`; see `not_backed_up` to warn first). Records are kept."""
    doomed = [p for p in _local_files(local) if p.suffix != _KEEP_SUFFIX]
    for path in doomed:
        path.unlink()
    return doomed


def not_backed_up(local: Path) -> list[Path]:
    """Local files with no verified NAS copy of their current content."""
    manifest = _load(local)
    return [
        p
        for p in _local_files(local)
        if p.suffix != _KEEP_SUFFIX and manifest.get(p.relative_to(local).as_posix()) != _sha256(p)
    ]


class BackgroundSync:
    """Runs `sync` off the scanning thread, so a slow or absent NAS never blocks a Session."""

    def __init__(self, local: Path, nas: Path, on_result):
        self._local, self._nas, self._on_result = local, nas, on_result
        self._requests: queue.Queue[bool] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def request(self) -> None:
        self._requests.put(True)

    def close(self) -> None:
        """Finish pending work, then stop."""
        self._requests.put(False)
        self._thread.join()

    def _run(self) -> None:
        while self._requests.get():
            try:
                self._on_result(sync(self._local, self._nas))
            except Exception as error:  # reported, never fatal to the Session
                self._on_result(error)


def _require_mounted(nas: Path) -> None:
    if not nas.is_dir():
        raise NasUnavailable(f"NAS folder not found (is the share mounted?): {nas}")


def _local_files(local: Path) -> list[Path]:
    return sorted(
        p
        for p in local.rglob("*")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(local).parts)
    )


def _copy_verified(source: Path, dest: Path, digest: str) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    try:
        # copy2 keeps the file's modification time: Ugreen Photos places
        # undated photos by it (ADR 0002), so a copy mustn't reset it.
        shutil.copy2(source, partial)
        if _sha256(partial) != digest:
            partial.unlink()
            return False
        partial.replace(dest)
        return True
    except OSError:
        partial.unlink(missing_ok=True)
        return False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _load(local: Path) -> dict[str, str]:
    path = local / MANIFEST
    return json.loads(path.read_text()) if path.exists() else {}


def _save(local: Path, manifest: dict[str, str]) -> None:
    tmp = local / (MANIFEST + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    tmp.replace(local / MANIFEST)
