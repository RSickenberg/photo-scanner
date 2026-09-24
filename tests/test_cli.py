import pytest
from typer.testing import CliRunner

from photoscan import cli
from tests.synthetic import FakePrint, make_scan


class FakeScanner:
    def __init__(self):
        self.calls = 0

    def scan(self, dpi, *, deep=False):
        self.calls += 1
        return make_scan([FakePrint((300, 300), (450, 300)), FakePrint((600, 1200), (300, 450))])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    local, nas = tmp_path / "local", tmp_path / "nas"
    nas.mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'output_dir = "{local}"\nnas_dir = "{nas}"\ndpi = 150\n')
    monkeypatch.setenv("PHOTOSCAN_CONFIG", str(cfg))
    scanner = FakeScanner()
    monkeypatch.setattr(cli, "make_scanner", lambda _: scanner)
    return local, nas, scanner


def test_a_session_scans_until_q_and_backs_everything_up(setup):
    local, nas, scanner = setup

    result = CliRunner().invoke(cli.app, ["session", "Grandma"], input="\n\nq\n")

    assert result.exit_code == 0, result.output
    assert scanner.calls == 2
    assert "Done: 4 Extract(s)" in result.output
    extracts = sorted(p.name for p in nas.glob("*/extracts/*.tif"))
    assert extracts == [
        "grandma_s001_p01.tif", "grandma_s001_p02.tif",
        "grandma_s002_p01.tif", "grandma_s002_p02.tif",
    ]  # fmt: skip


def test_rejected_preview_discards_the_scan(setup, monkeypatch):
    local, _, _ = setup
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)  # don't open Preview.app

    result = CliRunner().invoke(cli.app, ["session", "Grandma", "--preview"], input="\nr\n\n\nq\n")

    assert result.exit_code == 0, result.output
    assert [p.name for p in local.glob("*/scans/*")] == ["grandma_s001.tif"]


def test_rotate_command(setup):
    local, _, _ = setup
    CliRunner().invoke(cli.app, ["session", "Grandma"], input="\nq\n")
    extract = next(local.glob("*/extracts/*_p01.jpg"))

    result = CliRunner().invoke(cli.app, ["rotate", str(extract), "--degrees", "180"])

    assert result.exit_code == 0, result.output
