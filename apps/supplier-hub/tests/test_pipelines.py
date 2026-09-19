"""The four loop pipelines: what they may see, and what of their answers survives (§8.7, §13)."""

import json
from typing import Any

import pytest

from equivalence_core.comparators import (
    ComparisonStatus,
    Criticality,
    DecidedBy,
    HospitalSide,
    Judgment,
    SupplierSide,
    compare,
)
from equivalence_core.exchange.requirement import (
    AttributeOrigin,
    ProductHints,
    RequirementPayload,
)
from equivalence_core.facts import ResolvedRecord, ResolvedValue
from equivalence_core.templates import ComparisonRule, load_seed_templates
from equivalence_core.values import BoolValue, EnumValue, NumberValue, TextValue
from llm_client import FakeLLM
from supplier_hub.llm import (
    compare_text,
    extract_answer,
    judge,
    propose_attribute,
    simulate_supplier,
)
from supplier_hub.llm.fakes import fake_llm
from supplier_hub.llm.judge import SupplierFactView
from supplier_hub.llm.outputs import (
    AttributeJudgmentOut,
    AttributeProposalOut,
    JudgeOutput,
    Labels,
    QuestionDraft,
    TextReading,
    TextReadings,
)
from supplier_hub.llm.propose_attribute import ProposalRejected

SYRINGE = load_seed_templates()["syringe_single_use"]


def _requirement(**hints: Any) -> RequirementPayload:
    attributes = {
        "nominal_volume_ml": NumberValue(value=10, unit="ml"),
        "connector": EnumValue(value="LUER_LOCK"),
        "stopper_material": TextValue(value="Polyisopren"),
    }
    return RequirementPayload(
        article_ref="ar_5MZQ4K7T2V9C",
        template_code=SYRINGE.code,
        attributes=attributes,
        attribute_origin=dict.fromkeys(attributes, AttributeOrigin.EXTRACTED),
        unknown_attributes=tuple(k for k in SYRINGE.keys if k not in attributes),
        product_hints=ProductHints(**hints) if hints else None,
    )


def _supplier() -> ResolvedRecord:
    values = {
        "nominal_volume_ml": NumberValue(value=10, unit="ml"),
        "connector": EnumValue(value="LUER_LOCK"),
        "stopper_material": TextValue(value="latexfreier Stopfen"),
        "sterile": BoolValue(value=True),
    }
    return ResolvedRecord(
        attributes={
            key: ResolvedValue(value=value, fact_id=f"fct_{key}", source="CATALOG")
            for key, value in values.items()
        },
        unknown_attributes=tuple(k for k in SYRINGE.keys if k not in values),
        unavailable_attributes=(),
        identifiers=(),
    )


def _facts() -> list[SupplierFactView]:
    return [
        SupplierFactView(
            fact_id=value.fact_id,
            attribute_key=key,
            value=value.value.model_dump(mode="json"),
            scope="FAMILY",
        )
        for key, value in _supplier().attributes.items()
    ]


def _judge(llm: FakeLLM, requirement: RequirementPayload | None = None) -> judge.JudgeResult:
    requirement = requirement or _requirement()
    return judge.judge(
        llm,
        template=SYRINGE,
        requirement=requirement,
        comparator_results=compare(requirement, _supplier(), SYRINGE),
        supplier_facts=_facts(),
        supplier_product="BD Plastipak™ Luer-Lok™ 10 ml (300912)",
        past_answers=[],
        model="claude-opus-5",
        effort="high",
    )


def test_the_judge_decides_only_what_the_comparators_left_open() -> None:
    result = _judge(fake_llm())

    assert set(result.judgments) == {"stopper_material"}
    stopper = result.judgments["stopper_material"]
    assert (stopper.status, stopper.decided_by) == (ComparisonStatus.MATCH, DecidedBy.LLM)
    assert stopper.rationale


def test_the_judge_never_sees_who_asks_or_their_identifiers() -> None:
    llm = fake_llm()

    _judge(llm, _requirement(brand="B. Braun", gtin="04040456781234"))

    (request,) = llm.calls
    everything = request.system + request.user
    for secret in ("ar_5MZQ4K7T2V9C", "04040456781234", "B. Braun", "ten_ksp", "Kantonsspital"):
        assert secret not in everything
    assert (request.model, request.effort) == ("claude-opus-5", "high")


def test_an_invented_citation_turns_a_judgment_into_unknown() -> None:
    def inventing(request: Any) -> JudgeOutput:
        return JudgeOutput(
            judgments=[
                AttributeJudgmentOut(
                    attribute_key="stopper_material",
                    status="MATCH",
                    confidence=0.9,
                    rationale="Trust me.",
                    cited_fact_ids=["fct_does_not_exist"],
                ),
                # The comparators decided the connector; this is discarded.
                AttributeJudgmentOut(
                    attribute_key="connector",
                    status="MISMATCH",
                    confidence=0.9,
                    rationale="Overruling.",
                    cited_fact_ids=["fct_connector"],
                ),
            ],
            verdict="EQUIVALENT",
            confidence=0.5,
            rationale="-",
            questions=[
                QuestionDraft(
                    attribute_key="connector", addressee="SUPPLIER", text="?", language="de"
                )
            ],
            extra_concerns=["  ", "Frage 1?", "Frage 2?", "Frage 3?", "Frage 4?"],
        )

    result = _judge(FakeLLM({judge.PURPOSE: inventing}))

    assert set(result.judgments) == {"stopper_material"}
    assert result.judgments["stopper_material"].status is ComparisonStatus.UNKNOWN
    # A question about something that is not a gap is dropped too.
    assert result.questions == ()
    # Blank concerns are dropped and at most three are kept.
    assert result.extra_concerns == ("Frage 1?", "Frage 2?", "Frage 3?")


def test_the_judge_words_questions_for_askable_gaps() -> None:
    result = _judge(fake_llm())

    asked = {question.attribute_key for question in result.questions}
    assert {"mdr_class", "dehp_free"} <= asked
    assert all(question.language == "de" for question in result.questions)


def _extract(comment: str, key: str = "dehp_free") -> extract_answer.Extracted:
    return extract_answer.extract_answer(
        fake_llm(),
        question="Sind Zylinder und Stopfen frei von DEHP?",
        definition=SYRINGE.attribute(key),
        comment=comment,
        model="claude-haiku-4-5",
    )


def test_a_clear_comment_becomes_a_typed_value() -> None:
    extracted = _extract("Zylinder und Stopfen enthalten kein DEHP.")

    assert extracted.value == BoolValue(value=True)
    assert extracted.quote == "Zylinder und Stopfen enthalten kein DEHP."


def test_a_vague_comment_stays_unclear() -> None:
    assert _extract("Bitte wenden Sie sich an den Aussendienst.").value is None


def test_extraction_runs_without_thinking() -> None:
    llm = fake_llm()

    extract_answer.extract_answer(
        llm,
        question="?",
        definition=SYRINGE.attribute("dehp_free"),
        comment="kein DEHP",
        model="claude-haiku-4-5",
    )

    assert llm.calls[0].effort is None


def _propose(llm: FakeLLM, question: str) -> propose_attribute.Proposal:
    return propose_attribute.propose_attribute(
        llm,
        question=question,
        category="syringe_single_use",
        registry={attribute.key: attribute.labels.en for attribute in SYRINGE.attributes},
        identifier_keys=["gtin", "pzn", "himiv", "supplier_article_no"],
        forbidden_names=["BD", "B. Braun", "Plastipak", "Hospital H-7F3A"],
        model="claude-sonnet-5",
        effort="medium",
    )


def test_a_question_about_a_product_number_becomes_an_identifier() -> None:
    proposal = _propose(fake_llm(), "Wie lautet die GTIN der Handelseinheit?")

    assert (proposal.result, proposal.key, proposal.definition) == ("IDENTIFIER", "gtin", None)


def test_a_new_property_gets_a_neutral_definition() -> None:
    proposal = _propose(fake_llm(), "Enthält die Packung ein abziehbares Etikett?")

    assert proposal.result == "NEW"
    assert proposal.definition == {
        "key": "peel_off_label",
        "type": "bool",
        "unit": None,
        "options": [],
        "labels": {"de": "Abziehbares Dokumentationsetikett", "en": "Peel-off documentation label"},
    }


def test_a_known_property_maps_to_the_registry() -> None:
    proposal = _propose(fake_llm(), "Is it light protected?")

    assert (proposal.result, proposal.key) == ("EXISTING", "light_protected")


@pytest.mark.parametrize(
    "labels",
    [Labels(de="BD Etikett", en="BD label"), Labels(de="Etikett wie Plastipak", en="Label")],
)
def test_a_label_naming_a_brand_is_refused(labels: Labels) -> None:
    def branded(request: Any) -> AttributeProposalOut:
        return AttributeProposalOut(
            result="NEW",
            key="brand_label",
            value_type="bool",
            unit=None,
            options=None,
            labels=labels,
            rationale="-",
        )

    with pytest.raises(ProposalRejected, match="must not name"):
        _propose(FakeLLM({propose_attribute.PURPOSE: branded}), "?")


def test_the_simulator_answers_only_from_the_datasheet() -> None:
    questions = [
        {"question_id": "q1", "attribute_key": "mdr_class", "text": "MDR?"},
        {"question_id": "q2", "attribute_key": "inner_diameter_mm", "text": "ID?"},
    ]

    simulated = simulate_supplier.simulate_supplier(
        fake_llm(),
        questions=questions,
        datasheet={"mdr_class": {"value": "IIA", "family": True}},
        model="claude-haiku-4-5",
    )

    by_question = {answer.question_id: answer for answer in simulated.answers}
    assert by_question["q1"].value == "IIA" and by_question["q1"].applies_to_family
    assert by_question["q2"].cannot_provide
    assert json.dumps([a.model_dump() for a in simulated.answers])


def test_a_text_reading_keeps_only_decided_pairs_that_were_asked() -> None:
    worded = Judgment(
        attribute_key="special_scale",
        criticality=Criticality.MAJOR,
        rule=ComparisonRule.EXACT,
        status=ComparisonStatus.NEEDS_JUDGE,
        hospital=HospitalSide(
            value=TextValue(value="Skala 0,2 ml"), origin=AttributeOrigin.PURCHASER
        ),
        supplier=SupplierSide(value=TextValue(value="0.2-ml-Teilung"), fact_id="f1"),
    )

    def reply(request: Any) -> TextReadings:
        return TextReadings(
            readings=[
                TextReading(attribute_key="special_scale", status="MATCH", rationale="Same step."),
                TextReading(attribute_key="stopper_material", status="MISMATCH", rationale="-"),
            ]
        )

    llm = FakeLLM({compare_text.PURPOSE: reply})
    result = compare_text.compare_text(
        llm, template=SYRINGE, worded=[worded], model="claude-haiku-4-5"
    )

    assert set(result.judgments) == {"special_scale"}
    assert result.judgments["special_scale"].decided_by is DecidedBy.LLM
    (request,) = llm.calls
    assert request.effort is None
    assert "Skala 0,2 ml" in request.user
