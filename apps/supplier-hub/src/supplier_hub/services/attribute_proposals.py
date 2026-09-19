"""From a question without an attribute to a shared registry entry (ARCHITECTURE §7.2).

1. A purchaser's free question gets a proposal job (PROPOSE_ATTRIBUTE).
2. The proposal maps it to an existing key, an identifier definition or a new definition.
3. Sending the questions turns a new definition into a PROVISIONAL attribute, shared at once as
   information and never judged.
4. An operator approves it into its category with a criticality; only then does it count.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from equivalence_core.facts import SupplierSource
from equivalence_core.templates import AttributeDefinition as CoreAttribute
from equivalence_core.templates import RuleSettings
from equivalence_core.validation import InvalidValue, validate_value
from equivalence_core.values import TypedValue
from llm_client import LLMClient
from service_kit.errors import Conflict, NotFound, Unprocessable
from supplier_hub.core.settings import HubSettings
from supplier_hub.domain import state_machine
from supplier_hub.jobs import queue
from supplier_hub.llm import propose_attribute as pipeline
from supplier_hub.llm.propose_attribute import forbidden_name_in
from supplier_hub.models import (
    Assessment,
    AttributeDefinition,
    AttributeProposal,
    ItemFact,
    Organization,
    ProductFamily,
    Question,
    User,
)
from supplier_hub.models.assessments import QuestionStatus
from supplier_hub.models.events import EventType
from supplier_hub.models.jobs import JobKind
from supplier_hub.models.registry import (
    AttributeKind,
    AttributeOrigin,
    AttributeStatus,
    ProposalResult,
    ProposalStatus,
)
from supplier_hub.services import (
    attribute_registry,
    catalog,
    llm_calls,
    projection,
    supplier_catalog,
    templates,
)

_VALUE = TypeAdapter[TypedValue](TypedValue)


def open_for(
    session: Session, assessment: Assessment, question: Question, *, now: datetime
) -> AttributeProposal:
    proposal = AttributeProposal(
        question_id=question.id,
        assessment_id=assessment.id,
        category_code=assessment.template_code,
        created_at=now,
        updated_at=now,
    )
    session.add(proposal)
    session.flush()
    queue.enqueue(
        session,
        JobKind.PROPOSE_ATTRIBUTE,
        {"proposal_id": str(proposal.id)},
        now=now,
        dedupe_key=f"propose:{proposal.id}",
    )
    state_machine.record(
        session,
        assessment,
        EventType.ATTRIBUTE_PROPOSED,
        now=now,
        data={"question_id": str(question.id), "proposal_id": str(proposal.id)},
    )
    return proposal


def pending(session: Session, assessment: Assessment) -> int:
    """Proposals the job has not answered yet; sending waits for them (§7.2 step 2)."""
    query = select(func.count()).where(
        AttributeProposal.assessment_id == assessment.id,
        AttributeProposal.status == ProposalStatus.PENDING,
        AttributeProposal.result.is_(None),
    )
    return session.scalar(query) or 0


def run_proposal(
    session: Session,
    payload: Mapping[str, Any],
    now: datetime,
    *,
    llm: LLMClient | None,
    settings: HubSettings,
) -> None:
    """The PROPOSE_ATTRIBUTE job."""
    proposal = session.get(AttributeProposal, uuid.UUID(str(payload["proposal_id"])))
    if proposal is None or proposal.status != ProposalStatus.PENDING or proposal.result:
        return
    if llm is None:
        raise RuntimeError("proposing an attribute needs an LLM client")
    question = session.get(Question, proposal.question_id)
    assert question is not None
    registry = attribute_registry.definitions(session)
    # Nothing is written before the call: on SQLite a pending write would hold the one
    # write lock for as long as the model takes, and every request would wait for it.
    try:
        result = pipeline.propose_attribute(
            llm,
            question=question.text,
            category=proposal.category_code,
            registry={
                row.key: row.labels["en"]
                for row in registry
                if row.kind == AttributeKind.ATTRIBUTE and row.status != AttributeStatus.DEPRECATED
            },
            identifier_keys=[row.key for row in registry if row.kind == AttributeKind.IDENTIFIER],
            forbidden_names=_names(session),
            model=settings.propose_attribute_model,
            effort=settings.propose_attribute_effort,
        )
    except pipeline.ProposalRejected as exc:
        # The question is still sent; its answer is kept as text but becomes no fact.
        proposal.updated_at = now
        proposal.status = ProposalStatus.REJECTED
        proposal.review_note = f"rejected automatically: {exc}"
        return
    for record in result.records:
        proposal.llm_call_id = llm_calls.record_call(
            session, record, now=now, assessment_id=proposal.assessment_id
        )
    proposal.result = result.result
    proposal.updated_at = now
    if result.result == ProposalResult.EXISTING:
        proposal.matched_attribute_id = attribute_registry.by_key(session, result.key).id
        proposal.status = ProposalStatus.MATCHED
        _give_key(session, question, result.key)
    elif result.result == ProposalResult.IDENTIFIER:
        # A product number is not a comparable property: no attribute is created (D50).
        proposal.identifier_key = result.key
        proposal.status = ProposalStatus.ROUTED
        question.attribute_key = result.key
        question.expected_answer = {"type": "identifier", "scheme": result.key.upper()}
    else:
        proposal.proposal = {**(result.definition or {}), "rationale": result.rationale}


def make_provisional(session: Session, assessment: Assessment, *, now: datetime) -> None:
    """On send, a new definition becomes a registry row and its question gets the key.
    Withdrawn drafts never create attributes (§7.2 step 3)."""
    proposals = session.scalars(
        select(AttributeProposal).where(
            AttributeProposal.assessment_id == assessment.id,
            AttributeProposal.result == ProposalResult.NEW,
            AttributeProposal.status == ProposalStatus.PENDING,
        )
    )
    for proposal in proposals:
        question = session.get(Question, proposal.question_id)
        assert question is not None and proposal.proposal is not None
        if question.status == QuestionStatus.WITHDRAWN:
            continue
        attribute = _provisional_row(session, proposal.proposal, now=now)
        proposal.attribute_id = attribute.id
        proposal.status = ProposalStatus.PROVISIONAL
        proposal.updated_at = now
        _give_key(session, question, attribute.key)


def list_proposals(session: Session, status: str | None) -> Sequence[AttributeProposal]:
    query = select(AttributeProposal).order_by(AttributeProposal.created_at)
    if status is not None:
        query = query.where(AttributeProposal.status == status)
    return session.scalars(query).all()


@dataclass(frozen=True)
class Wording:
    """Labels and synonyms the curator corrects on approval; None keeps the proposal's."""

    labels: Mapping[str, str] | None = None
    synonyms: Mapping[str, str] | None = None


def approve(
    session: Session,
    proposal_id: uuid.UUID,
    settings: RuleSettings,
    *,
    wording: Wording | None = None,
    operator: User,
    now: datetime,
) -> AttributeProposal:
    """The attribute joins its category (§7.2 step 7); the template edit re-projects every
    family of the category, so the value moves out of the information."""
    proposal, attribute = _provisional(session, proposal_id)
    if wording is not None:
        _reword(session, attribute, wording)
    attribute.status = AttributeStatus.APPROVED
    attribute.approved_by = operator.id
    attribute.approved_at = now
    attribute.updated_at = now
    templates.add_attribute(
        session,
        proposal.category_code,
        attribute.key,
        settings,
        now=now,
        change_note=f"Added {attribute.key} from an attribute proposal",
        updated_by=operator.id,
    )
    _close(session, attribute, ProposalStatus.APPROVED, operator=operator, now=now)
    return proposal


def reject(
    session: Session, proposal_id: uuid.UUID, *, note: str, operator: User, now: datetime
) -> AttributeProposal:
    """The attribute is deprecated: its facts stay for audit but are no longer shown."""
    proposal, attribute = _provisional(session, proposal_id)
    attribute.status = AttributeStatus.DEPRECATED
    attribute.updated_at = now
    _close(session, attribute, ProposalStatus.REJECTED, operator=operator, now=now, note=note)
    _reproject(session, _families_with(session, attribute.key), now=now)
    return proposal


def merge(
    session: Session,
    proposal_id: uuid.UUID,
    target_key: str,
    *,
    note: str,
    operator: User,
    now: datetime,
) -> AttributeProposal:
    """The provisional attribute turns out to be one the registry has: its facts and questions
    move to that key (§7.2 step 6). All or nothing: one value the target cannot hold stops it."""
    proposal, attribute = _provisional(session, proposal_id)
    target = attribute_registry.by_key(session, target_key)
    if target.kind != AttributeKind.ATTRIBUTE or target.status != AttributeStatus.APPROVED:
        raise Unprocessable(f"{target_key} is not an approved attribute")
    if (target.value_type, target.unit) != (attribute.value_type, attribute.unit):
        raise Unprocessable(f"{target_key} holds {_shape(target)}, not {_shape(attribute)}")
    families = _families_with(session, attribute.key)
    moved = _moved_values(session, attribute, attribute_registry.as_core_attribute(target))
    for fact, value in moved:
        _move(session, fact, value, target.key, now=now)
    questions = select(Question).where(Question.attribute_key == attribute.key)
    for question in session.scalars(questions):
        _give_key(session, question, target.key)
    attribute.status = AttributeStatus.DEPRECATED
    attribute.merged_into_id = target.id
    attribute.updated_at = now
    _close(session, attribute, ProposalStatus.MERGED, operator=operator, now=now, note=note)
    _reproject(session, families, now=now)
    return proposal


def _provisional(
    session: Session, proposal_id: uuid.UUID
) -> tuple[AttributeProposal, AttributeDefinition]:
    proposal = session.get(AttributeProposal, proposal_id)
    if proposal is None:
        raise NotFound("proposal not found")
    if proposal.status != ProposalStatus.PROVISIONAL or proposal.attribute_id is None:
        raise Conflict("NOT_PROVISIONAL", "only a provisional attribute can be curated")
    attribute = session.get(AttributeDefinition, proposal.attribute_id)
    assert attribute is not None
    return proposal, attribute


def _reword(session: Session, attribute: AttributeDefinition, wording: Wording) -> None:
    if wording.labels is not None:
        if name := forbidden_name_in(wording.labels.values(), _names(session)):
            raise Unprocessable(f"labels must not name {name!r}")
        attribute.labels = dict(wording.labels)
    if wording.synonyms is not None:
        attribute.synonyms = dict(wording.synonyms)
    try:
        attribute_registry.as_core_attribute(attribute)
    except ValidationError as exc:
        raise Unprocessable(str(exc.errors()[0]["msg"]).removeprefix("Value error, ")) from exc


def _close(
    session: Session,
    attribute: AttributeDefinition,
    status: ProposalStatus,
    *,
    operator: User,
    now: datetime,
    note: str | None = None,
) -> None:
    """Every proposal that led to this attribute (two hospitals may ask the same) is decided."""
    siblings = select(AttributeProposal).where(
        AttributeProposal.attribute_id == attribute.id,
        AttributeProposal.status == ProposalStatus.PROVISIONAL,
    )
    for proposal in session.scalars(siblings):
        proposal.status = status
        proposal.reviewed_by = operator.id
        proposal.reviewed_at = now
        proposal.review_note = note
        proposal.updated_at = now
    session.flush()


def _moved_values(
    session: Session, attribute: AttributeDefinition, target: CoreAttribute
) -> list[tuple[ItemFact, TypedValue | None]]:
    facts = catalog.facts_with_key(session, attribute.key)
    moved: list[tuple[ItemFact, TypedValue | None]] = []
    problems: list[str] = []
    for fact in facts:
        if fact.value is None:
            moved.append((fact, None))
            continue
        try:
            moved.append((fact, validate_value(target, _VALUE.validate_python(fact.value))))
        except InvalidValue as exc:
            problems.append(f"{fact.raw_value or fact.value}: {exc}")
    if problems:
        raise Unprocessable(f"{target.key} cannot hold: " + "; ".join(problems))
    return moved


def _move(
    session: Session, fact: ItemFact, value: TypedValue | None, key: str, *, now: datetime
) -> None:
    """Re-added under the target key with its provenance; a value already there stays."""
    scope = {"family_id": fact.family_id, "variant_id": fact.variant_id}
    existing = next(
        (
            other
            for other in catalog.facts_of(session, **scope)
            if other.attribute_key == key and other.source == fact.source
        ),
        None,
    )
    replacement = existing or catalog.add_fact(
        session,
        key=key,
        value=value,
        raw=fact.raw_value,
        now=now,
        source=SupplierSource(fact.source),
        evidence_quote=fact.evidence_quote,
        confidence=fact.confidence,
        answer_id=fact.answer_id,
        created_by=fact.created_by,
        llm_call_id=fact.llm_call_id,
        model_id=fact.model_id,
        prompt_version=fact.prompt_version,
        **scope,
    )
    fact.superseded_by_id = replacement.id
    session.flush()


def _families_with(session: Session, key: str) -> list[ProductFamily]:
    families = (catalog.family_of(session, fact) for fact in catalog.facts_with_key(session, key))
    return list({family.id: family for family in families if family is not None}.values())


def _reproject(session: Session, families: Sequence[ProductFamily], *, now: datetime) -> None:
    for family in families:
        template = supplier_catalog.family_template(session, family)
        projection.rebuild_family(session, family, template, now=now)


def _shape(attribute: AttributeDefinition) -> str:
    return f"{attribute.value_type} ({attribute.unit})" if attribute.unit else attribute.value_type


def _provisional_row(
    session: Session, definition: Mapping[str, Any], *, now: datetime
) -> AttributeDefinition:
    # Two hospitals may ask the same thing before either is approved: one row serves both.
    existing = session.scalar(
        select(AttributeDefinition).where(AttributeDefinition.key == definition["key"])
    )
    if existing is not None:
        return existing
    row = AttributeDefinition(
        key=definition["key"],
        kind=AttributeKind.ATTRIBUTE,
        value_type=definition["type"],
        unit=definition["unit"],
        options=definition["options"] or None,
        labels=definition["labels"],
        synonyms={},
        status=AttributeStatus.PROVISIONAL,
        origin=AttributeOrigin.PROPOSAL,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def _give_key(session: Session, question: Question, key: str) -> None:
    definition = attribute_registry.as_core_attribute(attribute_registry.by_key(session, key))
    question.attribute_key = key
    question.expected_answer = attribute_registry.expected_answer(definition)


def _names(session: Session) -> list[str]:
    """What a shared label must never contain: suppliers, brands, hospitals and their aliases."""
    names: set[str] = set()
    for org in session.scalars(select(Organization)):
        names.update(filter(None, (org.name, org.supplier_facing_alias)))
    for family in session.scalars(select(ProductFamily)):
        names.update(filter(None, (family.manufacturer, family.brand_name)))
    return sorted(name.rstrip("®™ ") for name in names)
