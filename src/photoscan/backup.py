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
# Kept locally even when backed up: tiny, and needed to reopen a Session.
_NEVER_PRUNED = {"session.json"}


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
    """Delete local files whose NAS copy is re-verified identical right now."""
    _require_mounted(nas)
    manifest = _load(local)
    deleted = []
    for path in _local_files(local):
        rel = path.relative_to(local).as_posix()
        if path.name in _NEVER_PRUNED or rel not in manifest:
            continue
        remote = nas / rel
        if _sha256(path) == manifest[rel] and remote.exists() and _sha256(remote) == manifest[rel]:
            path.unlink()
            deleted.append(path)
    return deleted


def known_names(local: Path, session_path: Path) -> list[str]:
    """File names of a Session recorded as backed up, including locally pruned ones."""
    prefix = session_path.relative_to(local).as_posix() + "/"
    return [Path(rel).name for rel in _load(local) if rel.startswith(prefix)]


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
        shutil.copyfile(source, partial)
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
