import os

import pytest

from photoscan.backup import NasUnavailable, delete_all, not_backed_up, prune, sync


@pytest.fixture
def local(tmp_path):
    root = tmp_path / "local"
    session = root / "2026-09-24_grandma"
    (session / "scans").mkdir(parents=True)
    (session / "extracts").mkdir()
    (session / "session.json").write_text('{"label": "Grandma"}')
    (session / "scans" / "grandma_s001.tif").write_bytes(b"scan-1")
    (session / "extracts" / "grandma_s001_p01.tif").write_bytes(b"extract-1")
    (session / "extracts" / "grandma_s001_p01.jpg").write_bytes(b"extract-1-jpg")
    return root


@pytest.fixture
def nas(tmp_path):
    path = tmp_path / "nas"
    path.mkdir()
    return path


def test_sync_mirrors_every_file_to_the_nas(local, nas):
    report = sync(local, nas)

    assert len(report.copied) == 4
    assert (nas / "2026-09-24_grandma/scans/grandma_s001.tif").read_bytes() == b"scan-1"
    assert (nas / "2026-09-24_grandma/session.json").exists()


def test_second_sync_copies_nothing(local, nas):
    sync(local, nas)
    assert sync(local, nas).copied == []


def test_a_changed_file_is_copied_again(local, nas):
    sync(local, nas)
    extract = local / "2026-09-24_grandma/extracts/grandma_s001_p01.jpg"
    extract.write_bytes(b"rotated")

    report = sync(local, nas)

    assert [p.name for p in report.copied] == ["grandma_s001_p01.jpg"]
    assert (nas / "2026-09-24_grandma/extracts/grandma_s001_p01.jpg").read_bytes() == b"rotated"


def test_sync_reports_progress_on_the_files_it_copies(local, nas):
    sync(local, nas)
    extract = local / "2026-09-24_grandma/extracts/grandma_s001_p01.jpg"
    extract.write_bytes(b"rotated")
    seen = []

    def progress(pending):
        seen.append([(p.name, p.stat().st_size) for p in pending])
        return pending

    sync(local, nas, progress=progress)

    assert seen == [[("grandma_s001_p01.jpg", 7)]]  # only what needs copying, with its size


def test_sync_fails_clearly_when_the_nas_is_not_mounted(local, tmp_path):
    with pytest.raises(NasUnavailable):
        sync(local, tmp_path / "Volumes" / "photos")


def test_prune_deletes_only_files_verified_on_the_nas(local, nas):
    sync(local, nas)
    (local / "2026-09-24_grandma/scans/grandma_s002.tif").write_bytes(b"not backed up yet")
    (nas / "2026-09-24_grandma/extracts/grandma_s001_p01.tif").write_bytes(b"corrupted")

    deleted = prune(local, nas)

    session = local / "2026-09-24_grandma"
    assert sorted(p.name for p in deleted) == ["grandma_s001.tif", "grandma_s001_p01.jpg"]
    assert (session / "scans/grandma_s002.tif").exists()
    assert (session / "extracts/grandma_s001_p01.tif").exists()
    assert (session / "session.json").exists()


def test_prune_reports_progress_on_the_files_it_checks(local, nas):
    sync(local, nas)
    (local / "2026-09-24_grandma/scans/grandma_s002.tif").write_bytes(b"not backed up yet")
    seen = []

    def progress(candidates):
        seen.append(sorted(p.name for p in candidates))
        return candidates

    prune(local, nas, progress=progress)

    # backed-up images only: never records, nor files the NAS doesn't have
    assert seen == [["grandma_s001.tif", "grandma_s001_p01.jpg", "grandma_s001_p01.tif"]]


def test_sync_keeps_file_modification_times(local, nas):
    # Ugreen Photos places undated photos by their file date (ADR 0002).
    photo = local / "2026-09-24_grandma/extracts/grandma_s001_p01.jpg"
    os.utime(photo, (978307200, 978307200))

    sync(local, nas)

    copy = nas / "2026-09-24_grandma/extracts/grandma_s001_p01.jpg"
    assert copy.stat().st_mtime == 978307200


def test_forced_prune_deletes_everything_local_without_the_nas(local, tmp_path):
    session = local / "2026-09-24_grandma"

    deleted = delete_all(local)

    assert len(deleted) == 3  # never backed up, and no NAS at all
    assert not list(session.glob("*/*"))
    assert (session / "session.json").exists()  # kept: the Session's record


def test_not_backed_up_counts_files_missing_or_changed_since_the_backup(local, nas):
    sync(local, nas)
    (local / "2026-09-24_grandma/scans/grandma_s002.tif").write_bytes(b"new")
    (local / "2026-09-24_grandma/extracts/grandma_s001_p01.jpg").write_bytes(b"rotated")

    assert sorted(p.name for p in not_backed_up(local)) == [
        "grandma_s001_p01.jpg",
        "grandma_s002.tif",
    ]
