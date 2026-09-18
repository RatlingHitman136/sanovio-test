"""The hub's command line, run the way `make` runs it."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from supplier_hub import cli


def test_the_worker_starts_and_stops_on_its_own_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'hub.db'}")
    monkeypatch.setenv("LLM_MODE", "fake")
    # Instead of waiting for Ctrl+C, return at once: the test checks the wiring, not the wait.
    monkeypatch.setattr(cli, "_wait_until_interrupted", lambda: None)

    result = CliRunner().invoke(cli.app, ["worker"])

    assert result.exit_code == 0, result.output
    assert "worker running" in result.output
    assert "worker stopped" in result.output
    assert (tmp_path / "hub.db").exists()
