"""Requirements arriving from a node (ARCHITECTURE §16).

The payload is validated by the same core model the node built it with, and the hospital is
always taken from the token — never from the body.
"""

from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.orm import Session

from equivalence_core.exchange.requirement import RequirementPayload
from equivalence_core.templates import TemplateDefinition
from service_kit.errors import Unprocessable
from supplier_hub.services import templates


@dataclass(frozen=True)
class AcceptedRequirement:
    payload: RequirementPayload
    template: TemplateDefinition
    requirement_hash: str


def accept(session: Session, body: object) -> AcceptedRequirement:
    """A requirement the hub is willing to work with, plus the definition it is read against."""
    try:
        payload = RequirementPayload.model_validate(body)
    except ValidationError as exc:
        # `extra="forbid"` is what keeps names, prices and identifiers out (§16).
        raise Unprocessable(f"invalid requirement: {exc.error_count()} problem(s)") from exc
    try:
        template = templates.definition(session, payload.template_code)
    except Exception as exc:  # NotFound from the registry
        raise Unprocessable(f"unknown category {payload.template_code!r}") from exc
    unknown_keys = set(payload.attributes) - set(template.keys)
    if unknown_keys:
        raise Unprocessable(
            f"attributes outside {template.code}: {', '.join(sorted(unknown_keys))}"
        )
    return AcceptedRequirement(
        payload=payload, template=template, requirement_hash=payload.requirement_hash()
    )
