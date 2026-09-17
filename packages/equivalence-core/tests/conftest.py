from pathlib import Path
from typing import Any

import pytest
import yaml

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def sample_articles() -> list[dict[str, Any]]:
    data: dict[str, list[dict[str, Any]]] = yaml.safe_load(
        (FIXTURES / "sample_articles.yaml").read_text(encoding="utf-8")
    )
    return data["articles"]
