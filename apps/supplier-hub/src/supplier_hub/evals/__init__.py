"""Measurements of model quality on hand-labelled data (ARCHITECTURE §9); run with `make eval`."""

import json
from importlib import resources
from typing import Any


def load(name: str) -> list[dict[str, Any]]:
    """One hand-labelled case per line of a golden `.jsonl` file in this package."""
    text = (resources.files("supplier_hub") / "evals" / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]
