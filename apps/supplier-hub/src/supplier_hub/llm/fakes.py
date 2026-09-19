"""Deterministic stand-ins for every hub pipeline, so `LLM_MODE=fake` runs offline (§5, §13).

`normalize_item` answers from scripted readings shipped with the seed. The others are small
rule-based responders that read the request's own data block: they judge by evidence, word
questions from templates, extract only unmistakable values and answer from the synthetic
datasheets — deterministic, and never inventing anything a real model could not have read.
"""

import json
import re
from importlib import resources
from typing import Any

from equivalence_core.parsers import parse_number
from equivalence_core.parsers.wording import canonical_text
from llm_client import FakeLLM, StructuredRequest
from supplier_hub.llm import (
    compare_text,
    extract_answer,
    judge,
    normalize_item,
    propose_attribute,
    simulate_supplier,
)
from supplier_hub.llm.outputs import (
    AttributeJudgmentOut,
    AttributeProposalOut,
    ExtractedAnswer,
    JudgeOutput,
    Labels,
    NormalizedItem,
    NormalizeItems,
    QuestionDraft,
    SimulatedAnswer,
    SimulatedAnswers,
    TextReading,
    TextReadings,
)

_EMPTY: dict[str, Any] = {"category_code": None, "facts": []}
_BLOCKING = {"critical", "major"}
_YES = ("kein", "keine", "frei", "ohne", "ja", "yes", "erfüllt", "gemäss", "gemäß", "konform")
_NO = ("nein", "no ", "enthält")
_IDENTIFIER_WORDS = {
    "gtin": "gtin",
    "pzn": "pzn",
    "himiv": "himiv",
    "artikelnummer": "supplier_article_no",
}


def scripted_readings() -> dict[str, Any]:
    path = resources.files("supplier_hub") / "seed" / "fake_normalize_item.json"
    readings: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return readings


def fake_llm(readings: dict[str, Any] | None = None) -> FakeLLM:
    scripted = scripted_readings() if readings is None else readings
    return FakeLLM(
        {
            normalize_item.PURPOSE: lambda request: _normalize(request, scripted),
            judge.PURPOSE: _judge,
            extract_answer.PURPOSE: _extract,
            propose_attribute.PURPOSE: _propose,
            simulate_supplier.PURPOSE: _simulate,
            compare_text.PURPOSE: _compare_text,
        }
    )


def fake_normalizer(readings: dict[str, Any] | None = None) -> FakeLLM:
    """Kept for callers that only normalize; the same client answers every purpose."""
    return fake_llm(readings)


def _data(request: StructuredRequest[Any], tag: str = "data") -> Any:
    block = re.search(rf"<{tag}>(.*)</{tag}>", request.user, re.DOTALL)
    assert block is not None, f"the prompt always carries a <{tag}> block"
    return json.loads(block.group(1))


def _normalize(request: StructuredRequest[Any], scripted: dict[str, Any]) -> NormalizeItems:
    products = _data(request, "products")
    return NormalizeItems(
        items=[
            NormalizedItem(index=entry["index"], **scripted.get(entry["name"], _EMPTY))
            for entry in products
        ]
    )


def _judge(request: StructuredRequest[Any]) -> JudgeOutput:
    data = _data(request)
    facts: dict[str, str] = {}
    for fact in data["supplier_facts"]:
        facts.setdefault(fact["attribute_key"], fact["fact_id"])
    judgments = [
        AttributeJudgmentOut(
            attribute_key=key,
            # With evidence on the supplier side the fake accepts it; without, it cannot tell.
            status="MATCH" if key in facts else "UNKNOWN",
            confidence=0.8 if key in facts else 0.3,
            rationale=(
                "Both describe the same property in different words."
                if key in facts
                else "The supplier states nothing about this."
            ),
            cited_fact_ids=[facts[key]] if key in facts else [],
        )
        for key in data["needs_judgement"]
    ]
    gaps = data["gaps"]
    product = data["supplier_product"]
    questions = [
        QuestionDraft(
            attribute_key=gap["attribute_key"],
            addressee="SUPPLIER" if gap["missing"] in ("SUPPLIER", "BOTH") else "PURCHASER",
            text=(
                f"Welche Angabe gilt für „{gap['attribute_key']}“ bei {product}?"
                if gap["missing"] in ("SUPPLIER", "BOTH")
                else f"Welche Angabe gilt für „{gap['attribute_key']}“ bei Ihrem aktuellen Produkt?"
            ),
            language="de",
        )
        for gap in gaps
    ]
    blocking = any(gap["criticality"] in _BLOCKING for gap in gaps)
    return JudgeOutput(
        judgments=judgments,
        verdict="INSUFFICIENT_DATA" if blocking else "EQUIVALENT",
        confidence=0.7,
        rationale=(
            "Blocking information is missing." if blocking else "Nothing decisive is missing."
        ),
        questions=questions,
        extra_concerns=[],
    )


def _extract(request: StructuredRequest[Any]) -> ExtractedAnswer:
    data = _data(request)
    attribute = data["attribute"]
    text = str(data["answer"])
    lowered = f" {text.casefold()} "
    unclear = ExtractedAnswer(status="UNCLEAR", value=None, unit=None, quote=None)
    if attribute["type"] == "bool":
        if any(word in lowered for word in _YES):
            return ExtractedAnswer(status="VALUE", value=True, unit=None, quote=text)
        if any(word in lowered for word in _NO):
            return ExtractedAnswer(status="VALUE", value=False, unit=None, quote=text)
        return unclear
    if attribute["type"] == "number":
        found = re.search(r"\d+(?:[.,]\d+)?", text)
        if found is None:
            return unclear
        return ExtractedAnswer(
            status="VALUE",
            value=parse_number(found.group(0)),
            unit=attribute["unit"],
            quote=found.group(0),
        )
    if attribute["type"] == "enum":
        for option in attribute["options"]:
            if option.casefold() in lowered:
                return ExtractedAnswer(status="VALUE", value=option, unit=None, quote=option)
    return unclear


def _propose(request: StructuredRequest[Any]) -> AttributeProposalOut:
    data = _data(request)
    question = str(data["question"]).casefold()
    for word, key in _IDENTIFIER_WORDS.items():
        if word in question and key in data["identifier_keys"]:
            return AttributeProposalOut(
                result="IDENTIFIER",
                key=key,
                value_type=None,
                unit=None,
                options=None,
                labels=None,
                rationale="The question asks for a product number.",
            )
    for key, label in data["registry"].items():
        if label.casefold() in question:
            return AttributeProposalOut(
                result="EXISTING",
                key=key,
                value_type=None,
                unit=None,
                options=None,
                labels=None,
                rationale=f"The registry already has {key}.",
            )
    if "etikett" in question or "label" in question:
        return AttributeProposalOut(
            result="NEW",
            key="peel_off_label",
            value_type="bool",
            unit=None,
            options=None,
            labels=Labels(
                de="Abziehbares Dokumentationsetikett", en="Peel-off documentation label"
            ),
            rationale="No registry attribute describes a documentation label.",
        )
    return AttributeProposalOut(
        result="NEW",
        key="additional_detail",
        value_type="text",
        unit=None,
        options=None,
        labels=Labels(de="Zusatzangabe", en="Additional detail"),
        rationale="Nothing in the registry matches; a free-text attribute keeps the answer.",
    )


def _simulate(request: StructuredRequest[Any]) -> SimulatedAnswers:
    data = _data(request)
    sheet = data["datasheet"]
    answers = []
    for question in data["questions"]:
        entry = sheet.get(question["attribute_key"] or "")
        if entry is None:
            answers.append(
                SimulatedAnswer(
                    question_id=question["question_id"],
                    value=None,
                    unit=None,
                    comment="Nicht spezifiziert.",
                    cannot_provide=True,
                    applies_to_family=False,
                )
            )
            continue
        answers.append(
            SimulatedAnswer(
                question_id=question["question_id"],
                value=entry.get("value"),
                unit=entry.get("unit"),
                comment=entry.get("comment"),
                cannot_provide=False,
                applies_to_family=bool(entry.get("family", False)),
            )
        )
    return SimulatedAnswers(answers=answers)


def _compare_text(request: StructuredRequest[Any]) -> TextReadings:
    """Same meaning when at least half of the words are shared, after normalization."""
    readings = []
    for pair in _data(request)["pairs"]:
        ours = set(canonical_text(pair["hospital"]).split())
        theirs = set(canonical_text(pair["supplier"]).split())
        shared = len(ours & theirs) / max(len(ours | theirs), 1)
        readings.append(
            TextReading(
                attribute_key=pair["attribute_key"],
                status="MATCH" if shared >= 0.5 else "MISMATCH",
                rationale=f"{shared:.0%} of the words are shared.",
            )
        )
    return TextReadings(readings=readings)
