import json
import stat
from pathlib import Path

from typer.testing import CliRunner

from hospital_node.cli import app

runner = CliRunner()


def test_keygen_writes_private_and_public_key(tmp_path: Path) -> None:
    out = tmp_path / "node_ksp_ed25519.pem"

    result = runner.invoke(app, ["keygen", "--out", str(out), "--kid", "ksp-2026-09"])

    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    jwk = json.loads((tmp_path / "node_ksp_ed25519.pub.jwk.json").read_text())
    assert jwk["kid"] == "ksp-2026-09"
    assert "d" not in jwk
    assert "fingerprint" in result.output


def test_keygen_refuses_to_overwrite(tmp_path: Path) -> None:
    out = tmp_path / "node.pem"
    runner.invoke(app, ["keygen", "--out", str(out), "--kid", "k1"])

    result = runner.invoke(app, ["keygen", "--out", str(out), "--kid", "k2"])

    assert result.exit_code == 1
    assert "refusing to overwrite" in result.output
