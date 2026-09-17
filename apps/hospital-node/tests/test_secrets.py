from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from equivalence_core.exchange.keys import KeyFileError
from hospital_node.core.secrets import load_node_secrets
from hospital_node.core.settings import NodeSettings
from hospital_node.main import create_app


def test_secrets_load_and_hide_the_key(settings: NodeSettings) -> None:
    secrets = load_node_secrets(settings)

    assert secrets.signing_kid == "test-kid"
    assert "signing_key" not in repr(secrets)


def test_app_refuses_to_start_without_a_key(tmp_path: Path) -> None:
    settings = NodeSettings(node_signing_key_file=tmp_path / "absent.pem", node_signing_kid="k")

    with pytest.raises(KeyFileError, match="not found"), TestClient(create_app(settings)):
        pass


def test_app_refuses_a_key_readable_by_others(settings: NodeSettings) -> None:
    settings.node_signing_key_file.chmod(0o644)

    with pytest.raises(KeyFileError, match="mode 644"), TestClient(create_app(settings)):
        pass
