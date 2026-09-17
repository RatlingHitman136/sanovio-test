"""One canonical JSON form for every hash the node and the hub compare."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel


def canonical_json(obj: Any) -> str:
    return json.dumps(
        _normalize(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def _normalize(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return _normalize(obj.model_dump(mode="json"))
    if isinstance(obj, Mapping):
        return {str(key): _normalize(value) for key, value in obj.items()}
    if isinstance(obj, list | tuple):
        return [_normalize(item) for item in obj]
    # 10 and 10.0 are the same value; without this they would hash differently.
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    return obj
