import pytest

from photoscan.backup import NasUnavailable, known_names, prune, sync


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


def test_known_names_remember_pruned_files(local, nas):
    sync(local, nas)
    prune(local, nas)

    assert "grandma_s001.tif" in known_names(local, local / "2026-09-24_grandma")
