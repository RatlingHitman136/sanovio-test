"""Attribute curation: a provisional attribute is approved into its category, merged into one
the registry has, or rejected (§7.2 step 6). Only an operator decides how much it counts."""

import uuid

from fastapi import APIRouter

from equivalence_core.templates import RuleSettings
from supplier_hub.api.deps import Context, DbSession, Operator
from supplier_hub.models import AttributeProposal, Question
from supplier_hub.models.audit import AuditAction
from supplier_hub.models.registry import ProposalStatus
from supplier_hub.schemas.admin import (
    AttributeProposalView,
    ProposalApproval,
    ProposalMerge,
    ProposalRejection,
)
from supplier_hub.services import attribute_proposals, catalog, operator_audit
from supplier_hub.services.attribute_proposals import Wording

router = APIRouter(prefix="/attribute-proposals")


@router.get("")
def list_attribute_proposals(
    session: DbSession, status: ProposalStatus | None = None
) -> list[AttributeProposalView]:
    return [_proposal(session, row) for row in attribute_proposals.list_proposals(session, status)]


@router.post("/{proposal_id}/approve")
def approve_attribute_proposal(
    proposal_id: uuid.UUID,
    body: ProposalApproval,
    context: Context,
    session: DbSession,
    operator: Operator,
) -> AttributeProposalView:
    settings = RuleSettings.model_validate(body.model_dump(include=set(RuleSettings.model_fields)))
    wording = Wording(
        labels=body.labels.model_dump() if body.labels is not None else None,
        synonyms=body.synonyms,
    )
    proposal = attribute_proposals.approve(
        session, proposal_id, settings, wording=wording, operator=operator, now=context.clock()
    )
    _audit(
        session,
        operator,
        AuditAction.PROPOSAL_APPROVED,
        proposal,
        context,
        settings.model_dump(mode="json"),
    )
    return _proposal(session, proposal)


@router.post("/{proposal_id}/merge")
def merge_attribute_proposal(
    proposal_id: uuid.UUID,
    body: ProposalMerge,
    context: Context,
    session: DbSession,
    operator: Operator,
) -> AttributeProposalView:
    proposal = attribute_proposals.merge(
        session,
        proposal_id,
        body.attribute_key,
        note=body.note,
        operator=operator,
        now=context.clock(),
    )
    _audit(
        session,
        operator,
        AuditAction.PROPOSAL_MERGED,
        proposal,
        context,
        {"into": body.attribute_key},
    )
    return _proposal(session, proposal)


@router.post("/{proposal_id}/reject")
def reject_attribute_proposal(
    proposal_id: uuid.UUID,
    body: ProposalRejection,
    context: Context,
    session: DbSession,
    operator: Operator,
) -> AttributeProposalView:
    proposal = attribute_proposals.reject(
        session, proposal_id, note=body.note, operator=operator, now=context.clock()
    )
    _audit(session, operator, AuditAction.PROPOSAL_REJECTED, proposal, context, {})
    return _proposal(session, proposal)


def _audit(
    session: DbSession,
    operator: Operator,
    action: AuditAction,
    proposal: AttributeProposal,
    context: Context,
    data: dict[str, object],
) -> None:
    operator_audit.record(
        session,
        operator,
        action,
        target_type="attribute_proposal",
        target_id=proposal.id,
        now=context.clock(),
        data={"category": proposal.category_code, **data},
    )


def _proposal(session: DbSession, row: AttributeProposal) -> AttributeProposalView:
    question = session.get(Question, row.question_id)
    assert question is not None
    key = question.attribute_key
    return AttributeProposalView(
        id=row.id,
        question_id=row.question_id,
        question_text=question.text,
        category_code=row.category_code,
        result=row.result,
        status=row.status,
        proposal=row.proposal,
        attribute_key=key,
        identifier_key=row.identifier_key,
        review_note=row.review_note,
        value_count=len(catalog.facts_with_key(session, key)) if key else 0,
        created_at=row.created_at,
    )
