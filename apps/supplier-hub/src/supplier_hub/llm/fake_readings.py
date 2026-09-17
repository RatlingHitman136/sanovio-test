"""The scripted `normalize_item` answers that make `LLM_MODE=fake` deterministic (§5).

They say what the catalog prose says and nothing more, so an offline seed produces the same
facts a real Sonnet 5 run would — including one deliberately invented quote, which the
pipeline's checks drop.
"""

import json
import re
from importlib import resources
from typing import Any

from llm_client import FakeLLM, StructuredRequest
from supplier_hub.llm.normalize_item import PURPOSE
from supplier_hub.llm.outputs import NormalizedItem, NormalizeItems

_EMPTY: dict[str, Any] = {"category_code": None, "facts": []}


def scripted_readings() -> dict[str, Any]:
    path = resources.files("supplier_hub") / "seed" / "fake_normalize_item.json"
    readings: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return readings


def fake_normalizer(readings: dict[str, Any] | None = None) -> FakeLLM:
    scripted = scripted_readings() if readings is None else readings

    def respond(request: StructuredRequest[Any]) -> NormalizeItems:
        block = re.search(r"<products>(.*)</products>", request.user, re.DOTALL)
        assert block is not None, "the prompt always carries a products block"
        products = json.loads(block.group(1))
        return NormalizeItems(
            items=[
                NormalizedItem(index=entry["index"], **scripted.get(entry["name"], _EMPTY))
                for entry in products
            ]
        )

    return FakeLLM({PURPOSE: respond})
