"""One judgment round, the ASSESS job (ARCHITECTURE §8, §11; §19 step 6).

In order: identifier evidence (a same-trade-item match ends the round with no comparator and
no judge call, D51) → comparators → the judge, only for what they left open → verdict rules →
stop conditions → questions for the gaps someone can fill. Everything the round saw is stored
with it, so any round can be replayed after the catalog or the template has moved on.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.comparators import (
    WORDED_DIFFERENTLY,
    ComparisonStatus,
    Judgment,
    MissingSide,
    compare,
)
from equivalence_core.exchange.requirement import RequirementPayload
from equivalence_core.facts import ResolvedRecord
from equivalence_core.hashing import sha256_hex
from equivalence_core.identifier_evidence import IdentifierEvidence, identifier_evidence
from equivalence_core.templates import TemplateDefinition
from equivalence_core.verdict_rules import (
    BLOCKING,
    Verdict,
    VerdictOutcome,
    apply_judgments,
    decide,
)
from llm_client import LLMClient
from supplier_hub.core.settings import HubSettings
from supplier_hub.domain import state_machine
from supplier_hub.domain.stop_conditions import next_step
from supplier_hub.llm import judge as judge_pipeline
from supplier_hub.llm.compare_text import compare_text
from supplier_hub.llm.judge import JudgeResult, SupplierFactView
from supplier_hub.llm.outputs import QuestionDraft
from supplier_hub.models import Answer, Assessment, AssessmentRound, Question, Requirement
from supplier_hub.models.assessments import (
    Addressee,
    AssessmentStatus,
    QuestionOrigin,
    QuestionStatus,
)
from supplier_hub.models.events import EventType
from supplier_hub.services import (
    attribute_proposals,
    attribute_registry,
    llm_calls,
    projection,
    templates,
)


@dataclass(frozen=True)
class Judged:
    result: JudgeResult
    call_id: uuid.UUID | None


@dataclass(frozen=True)
class RoundInput:
    requirement: Requirement
    payload: RequirementPayload
    template: TemplateDefinition
    record: ResolvedRecord


def run_round(
    session: Session,
    payload: Mapping[str, Any],
    now: datetime,
    *,
    llm: LLMClient | None,
    settings: HubSettings,
) -> None:
    """The ASSESS job handler."""
    assessment = session.get(Assessment, uuid.UUID(str(payload["assessment_id"])))
    if assessment is None or assessment.status != AssessmentStatus.ASSESSING:
        return  # cancelled or already moved on while the job waited
    inputs = _inputs(session, assessment)
    evidence = identifier_evidence(
        inputs.payload.product_hints,
        inputs.record.identifiers,
        assessment.variant.family.manufacturer,
    )

    judged: Judged | None = None
    if evidence is IdentifierEvidence.SAME_TRADE_ITEM:
        judgments: tuple[Judgment, ...] = ()
    else:
        judgments = compare(inputs.payload, inputs.record, inputs.template)
        judgments = _read_worded_text(session, assessment, inputs, judgments, llm, settings, now)
        if _needs_the_judge(judgments):
            if llm is None:
                raise RuntimeError("the judge is needed but no LLM client is configured")
            judged = _judge(session, assessment, inputs, judgments, llm, settings, now)
            judgments = apply_judgments(judgments, judged.result.judgments).judgments
    outcome = decide(judgments, evidence)

    round_no = assessment.current_round + 1
    input_hash = sha256_hex(
        [
            inputs.requirement.requirement_hash,
            inputs.record.record_hash(),
            inputs.template.definition_hash,
        ]
    )
    previous = assessment.rounds[-1].input_hash if assessment.rounds else None
    askable = _askable(judgments)
    step = next_step(
        outcome,
        round_no=round_no,
        max_rounds=assessment.max_rounds,
        input_hash=input_hash,
        previous_input_hash=previous,
        askable_gaps=len(askable),
    )
    round_row = AssessmentRound(
        assessment_id=assessment.id,
        round_no=round_no,
        requirement_id=inputs.requirement.id,
        supplier_record_hash=inputs.record.record_hash(),
        input_hash=input_hash,
        input_snapshot={
            "requirement": inputs.payload.model_dump(mode="json"),
            "supplier": inputs.record.model_dump(mode="json"),
            "template": inputs.template.model_dump(mode="json"),
        },
        identifier_evidence=evidence,
        attribute_judgments=[judgment.model_dump(mode="json") for judgment in judgments],
        rule_verdict=outcome.verdict,
        llm_verdict=judged.result.verdict if judged else None,
        llm_confidence=_confidence(judged),
        # The model's own verdict is only a cross-check; a difference is flagged, never obeyed.
        disagreement=bool(
            judged and judged.result.verdict and judged.result.verdict is not outcome.verdict
        ),
        rationale=judged.result.rationale if judged else _reason(outcome),
        extra_concerns=list(judged.result.extra_concerns) if judged else [],
        outcome_status=step.status,
        definition_hash=inputs.template.definition_hash,
        prompt_version=judge_pipeline.PROMPT_VERSION if judged else None,
        model_id=settings.judge_model if judged else None,
        llm_call_id=judged.call_id if judged else None,
        created_at=now,
    )
    session.add(round_row)
    session.flush()

    question_ids: list[str] = []
    if step.status is AssessmentStatus.NEEDS_QUESTION_REVIEW:
        drafts = judged.result.questions if judged else ()
        created = _draft_questions(session, assessment, round_row, askable, drafts, inputs, now)
        if judged:
            created += _concern_questions(session, assessment, round_row, judged.result, now)
        question_ids = [str(question.id) for question in created]

    assessment.current_round = round_no
    assessment.manual_reason = step.manual_reason
    if step.status is AssessmentStatus.PROPOSED_RESOLUTION:
        assessment.proposed_verdict = outcome.verdict
    state_machine.transition(
        session,
        assessment,
        step.status,
        now=now,
        event=EventType.ROUND_COMPLETED,
        data={
            "round_no": round_no,
            "rule_verdict": outcome.verdict,
            "identifier_evidence": evidence,
            "questions": question_ids,
            "manual_reason": step.manual_reason,
        },
    )


def _inputs(session: Session, assessment: Assessment) -> RoundInput:
    requirement = assessment.current_requirement
    assert requirement is not None, "an assessment always has a current requirement"
    template = templates.definition(session, assessment.template_code)
    return RoundInput(
        requirement=requirement,
        payload=RequirementPayload.model_validate(requirement.payload),
        template=template,
        record=projection.resolve(session, assessment.variant, template),
    )


def _read_worded_text(
    session: Session,
    assessment: Assessment,
    inputs: RoundInput,
    judgments: tuple[Judgment, ...],
    llm: LLMClient | None,
    settings: HubSettings,
    now: datetime,
) -> tuple[Judgment, ...]:
    """Text the comparators could not settle by spelling, read by meaning in one small call
    (§8). What the model cannot tell stays open for the judge."""
    worded = [
        judgment
        for judgment in judgments
        if judgment.status is ComparisonStatus.NEEDS_JUDGE and judgment.detail == WORDED_DIFFERENTLY
    ]
    if not worded or llm is None or decide(judgments).verdict is Verdict.NOT_EQUIVALENT:
        return judgments
    reading = compare_text(
        llm, template=inputs.template, worded=worded, model=settings.compare_text_model
    )
    for record in reading.records:
        llm_calls.record_call(session, record, now=now, assessment_id=assessment.id)
    return apply_judgments(judgments, reading.judgments).judgments


def _needs_the_judge(judgments: Sequence[Judgment]) -> bool:
    """A critical mismatch already decides the round; otherwise the judge is asked when there
    is something to judge or a question to word (§8.4)."""
    if decide(judgments).verdict is Verdict.NOT_EQUIVALENT:
        return False
    return any(
        judgment.status is ComparisonStatus.NEEDS_JUDGE
        or (judgment.missing is not None and judgment.askable)
        for judgment in judgments
    )


def _judge(
    session: Session,
    assessment: Assessment,
    inputs: RoundInput,
    judgments: Sequence[Judgment],
    llm: LLMClient,
    settings: HubSettings,
    now: datetime,
) -> Judged:
    facts = [
        SupplierFactView(
            fact_id=resolved.fact_id,
            attribute_key=key,
            value=resolved.value.model_dump(mode="json"),
            scope=resolved.scope,
        )
        for key, resolved in inputs.record.attributes.items()
    ]
    variant = assessment.variant
    result = judge_pipeline.judge(
        llm,
        template=inputs.template,
        requirement=inputs.payload,
        comparator_results=judgments,
        supplier_facts=facts,
        supplier_product=f"{variant.label} ({variant.article_no})",
        past_answers=_past_answers(session, assessment),
        model=settings.judge_model,
        effort=settings.judge_effort,
    )
    call_ids = [
        llm_calls.record_call(session, record, now=now, assessment_id=assessment.id)
        for record in result.records
    ]
    return Judged(result, call_ids[-1] if call_ids else None)


def _askable(judgments: Sequence[Judgment]) -> list[Judgment]:
    """Blocking gaps someone could still fill: unknown (not unavailable), and not withheld."""
    return [
        judgment
        for judgment in judgments
        if judgment.criticality in BLOCKING
        and judgment.status is ComparisonStatus.UNKNOWN
        and judgment.missing is not None
        and judgment.askable
    ]


def _draft_questions(
    session: Session,
    assessment: Assessment,
    round_row: AssessmentRound,
    gaps: Sequence[Judgment],
    drafts: Sequence[QuestionDraft],
    inputs: RoundInput,
    now: datetime,
) -> list[Question]:
    worded: dict[tuple[str, str], QuestionDraft] = {
        (draft.attribute_key, draft.addressee): draft for draft in drafts
    }
    open_keys = {
        (question.attribute_key, question.addressee)
        for question in assessment.questions
        if question.status in (QuestionStatus.DRAFT, QuestionStatus.SENT)
    }
    created = []
    for gap in gaps:
        for addressee in _addressees(gap.missing):
            if (gap.attribute_key, addressee) in open_keys:
                continue
            draft = worded.get((gap.attribute_key, addressee.value))
            question = Question(
                assessment_id=assessment.id,
                round_id=round_row.id,
                addressee=addressee,
                attribute_key=gap.attribute_key,
                text=draft.text if draft else _template_text(gap, addressee, assessment, inputs),
                language=draft.language if draft else "de",
                expected_answer=attribute_registry.expected_answer(
                    inputs.template.attribute(gap.attribute_key)
                ),
                rationale=gap.detail or f"{gap.criticality} attribute without a value",
                origin=QuestionOrigin.LLM if draft else QuestionOrigin.TEMPLATE,
                status=QuestionStatus.DRAFT,
                created_at=now,
            )
            session.add(question)
            created.append(question)
    session.flush()
    return created


def _concern_questions(
    session: Session,
    assessment: Assessment,
    round_row: AssessmentRound,
    result: JudgeResult,
    now: datetime,
) -> list[Question]:
    """The judge's extra concerns have no attribute yet; each gets one proposed (§7.2)."""
    asked = {question.text for question in assessment.questions}
    created = []
    for text in result.extra_concerns:
        if text in asked:
            continue
        question = Question(
            assessment_id=assessment.id,
            round_id=round_row.id,
            addressee=Addressee.SUPPLIER,
            attribute_key=None,
            text=text,
            language="de",
            expected_answer={"type": "text"},
            rationale="extra concern raised by the judge",
            origin=QuestionOrigin.LLM,
            status=QuestionStatus.DRAFT,
            created_at=now,
        )
        session.add(question)
        session.flush()
        attribute_proposals.open_for(session, assessment, question, now=now)
        created.append(question)
    return created


def _addressees(missing: MissingSide | None) -> tuple[Addressee, ...]:
    match missing:
        case MissingSide.SUPPLIER:
            return (Addressee.SUPPLIER,)
        case MissingSide.HOSPITAL:
            return (Addressee.PURCHASER,)
        case MissingSide.BOTH:
            return (Addressee.SUPPLIER, Addressee.PURCHASER)
    return ()


def _template_text(
    gap: Judgment, addressee: Addressee, assessment: Assessment, inputs: RoundInput
) -> str:
    """The fallback wording when the judge gave none; never mentions the hospital (§8.6)."""
    label = inputs.template.attribute(gap.attribute_key).labels
    if addressee is Addressee.SUPPLIER:
        variant = assessment.variant
        return f"Bitte geben Sie „{label.de}“ für {variant.label} ({variant.article_no}) an."
    return f"Welche Angabe gilt für „{label.de}“ bei Ihrem aktuellen Produkt?"


def _past_answers(session: Session, assessment: Assessment) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Question, Answer)
        .join(Answer, Answer.question_id == Question.id)
        .where(Question.assessment_id == assessment.id, Answer.is_draft.is_(False))
    ).all()
    return [
        {
            "attribute_key": question.attribute_key,
            "question": question.text,
            "answer": answer.value,
            "comment": answer.comment,
            "cannot_provide": answer.cannot_provide,
        }
        for question, answer in rows
    ]


def _confidence(judged: Judged | None) -> Decimal | None:
    if judged is None or judged.result.confidence is None:
        return None
    return Decimal(str(round(judged.result.confidence, 2)))


def _reason(outcome: VerdictOutcome) -> str:
    return {
        "SAME_TRADE_ITEM": "A check-digit-valid identifier matches on both sides.",
        "CRITICAL_MISMATCH": f"Critical mismatch: {', '.join(outcome.mismatches)}.",
    }.get(outcome.reason, outcome.reason)
