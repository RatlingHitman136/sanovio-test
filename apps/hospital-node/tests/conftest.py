from pathlib import Path

import pytest

from equivalence_core.exchange.keys import generate_private_key, write_private_key
from hospital_node.core.settings import NodeSettings


@pytest.fixture
def settings(tmp_path: Path) -> NodeSettings:
    key_file = tmp_path / "node.pem"
    write_private_key(generate_private_key(), key_file)
    return NodeSettings(node_signing_key_file=key_file, node_signing_kid="test-kid")
