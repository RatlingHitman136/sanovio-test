"""`propose_attribute`: a question without an attribute → an existing key, a new definition or
an identifier definition (ARCHITECTURE §7.2 step 2)."""

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from llm_client import CallRecord, Effort, LLMClient, StructuredRequest, render
from supplier_hub.llm.outputs import AttributeProposalOut

PURPOSE = "PROPOSE_ATTRIBUTE"
PROMPT_VERSION = "propose_attribute_v1"
_KEY = re.compile(r"^[a-z][a-z0-9_]{2,60}$")


class ProposalRejected(ValueError):
    """The model's proposal is not usable; the message says why, for the operator."""


@dataclass(frozen=True)
class Proposal:
    result: str
    key: str
    definition: dict[str, Any] | None
    rationale: str
    records: tuple[CallRecord, ...]


def propose_attribute(
    llm: LLMClient,
    *,
    question: str,
    category: str,
    registry: Mapping[str, str],
    identifier_keys: Iterable[str],
    forbidden_names: Iterable[str],
    model: str,
    effort: Effort,
) -> Proposal:
    """`registry` maps each attribute key to its English label; names never go into labels."""
    identifiers = sorted(identifier_keys)
    data = {
        "question": question,
        "category": category,
        "registry": dict(sorted(registry.items())),
        "identifier_keys": identifiers,
    }
    request = StructuredRequest(
        purpose=PURPOSE,
        model=model,
        effort=effort,
        prompt_version=PROMPT_VERSION,
        system=render("supplier_hub.llm", f"{PROMPT_VERSION}.j2"),
        user="<data>\n" + json.dumps(data, ensure_ascii=False, indent=1) + "\n</data>",
        output_type=AttributeProposalOut,
        max_tokens=4096,
    )
    result = llm.parse(request)
    out = result.output
    if out is None:
        raise ProposalRejected("the model gave no usable proposal")
    if out.result == "EXISTING":
        if out.key not in registry:
            raise ProposalRejected(f"{out.key!r} is not in the registry")
        return Proposal("EXISTING", out.key, None, out.rationale, result.records)
    if out.result == "IDENTIFIER":
        if out.key not in identifiers:
            raise ProposalRejected(f"{out.key!r} is not an identifier definition")
        return Proposal("IDENTIFIER", out.key, None, out.rationale, result.records)
    return Proposal(
        "NEW",
        out.key,
        _new_definition(out, registry, forbidden_names),
        out.rationale,
        result.records,
    )


def _new_definition(
    out: AttributeProposalOut, registry: Mapping[str, str], forbidden_names: Iterable[str]
) -> dict[str, Any]:
    if not _KEY.match(out.key) or out.key in registry:
        raise ProposalRejected(f"{out.key!r} is not a new snake_case key")
    if out.value_type is None or out.labels is None:
        raise ProposalRejected("a new attribute needs a type and labels")
    if out.value_type == "number" and not out.unit:
        raise ProposalRejected("a number attribute needs a unit")
    if out.value_type == "enum" and not out.options:
        raise ProposalRejected("an enum attribute needs options")
    if name := forbidden_name_in((out.labels.de, out.labels.en), forbidden_names):
        raise ProposalRejected(f"labels must not name {name!r}")
    return {
        "key": out.key,
        "type": out.value_type,
        "unit": out.unit,
        "options": out.options or [],
        "labels": out.labels.model_dump(),
    }


def forbidden_name_in(labels: Iterable[str], forbidden_names: Iterable[str]) -> str | None:
    """Neutral labels: a registry entry is shared by every hospital and every supplier (§7.2)."""
    text = " ".join(labels).casefold()
    return next((name for name in forbidden_names if name and name.casefold() in text), None)
