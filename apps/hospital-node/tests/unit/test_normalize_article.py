from typing import Any

import pytest

from equivalence_core.templates import TemplateDefinition, load_seed_templates
from equivalence_core.values import BoolValue, EnumValue, NumberValue
from hospital_node.llm.normalize_article import PURPOSE, normalize_batch
from hospital_node.llm.outputs import NormalizeBatch, NormalizedArticle, ProposedFact
from llm_client import FakeLLM, StructuredRequest
from node_fixtures import names_in

NAME = "Einmalspritze 10 ml Luer-Lock steril"


@pytest.fixture(scope="module")
def templates() -> dict[str, TemplateDefinition]:
    return load_seed_templates()


def _fact(key: str, value: Any, quote: str, unit: str | None = None) -> ProposedFact:
    return ProposedFact(attribute_key=key, value=value, unit=unit, quote=quote, confidence=0.8)


def _answering(*facts: ProposedFact, category: str | None = "syringe_single_use") -> FakeLLM:
    def respond(request: StructuredRequest[Any]) -> NormalizeBatch:
        return NormalizeBatch(
            articles=[NormalizedArticle(index=0, category_code=category, facts=list(facts))]
        )

    return FakeLLM({PURPOSE: respond})


def _read(llm: FakeLLM, templates: dict[str, TemplateDefinition], name: str = NAME) -> Any:
    result = normalize_batch(llm, [name], templates, model="claude-sonnet-5", effort="medium")
    assert result.readings is not None
    return result.readings[0]


def test_valid_facts_are_typed_and_normalized(templates: dict[str, TemplateDefinition]) -> None:
    llm = _answering(
        _fact("connector", "Luer-Lock", "Luer-Lock"),
        _fact("nominal_volume_ml", 0.01, "10 ml", unit="l"),
        _fact("sterile", True, "steril"),
    )

    reading = _read(llm, templates)

    assert reading.category_code == "syringe_single_use"
    assert {f.attribute_key: f.value for f in reading.facts} == {
        "connector": EnumValue(value="LUER_LOCK"),
        "nominal_volume_ml": NumberValue(value=10, unit="ml"),
        "sterile": BoolValue(value=True),
    }


@pytest.mark.parametrize(
    "fact",
    [
        _fact("sterile", True, "sterilisiert"),  # quote not in the name
        _fact("gauge", 21, "10 ml", unit="G"),  # not an attribute of the category
        _fact("connector", "Bajonett", "Luer-Lock"),  # not an option
        _fact("sterile", "yes", "steril"),  # wrong type
        _fact("nominal_volume_ml", 10, "10 ml", unit="G"),  # unit that cannot convert
        _fact("sterile", True, " "),  # empty quote
    ],
)
def test_unchecked_facts_are_dropped(
    templates: dict[str, TemplateDefinition], fact: ProposedFact
) -> None:
    assert _read(_answering(fact), templates).facts == ()


def test_an_unknown_category_drops_the_whole_answer(
    templates: dict[str, TemplateDefinition],
) -> None:
    reading = _read(_answering(_fact("sterile", True, "steril"), category="wipes"), templates)

    assert reading.category_code is None
    assert reading.facts == ()


def test_only_names_are_sent(templates: dict[str, TemplateDefinition]) -> None:
    llm = _answering()

    normalize_batch(
        llm, [NAME, "Kanüle 0,8 × 40 mm"], templates, model="claude-sonnet-5", effort="medium"
    )

    (request,) = llm.calls
    assert names_in(request) == [NAME, "Kanüle 0,8 × 40 mm"]
    assert "hypodermic_needle" in request.system
    assert request.model == "claude-sonnet-5"
    assert request.effort == "medium"


def test_a_missing_article_in_the_answer_reads_as_nothing(
    templates: dict[str, TemplateDefinition],
) -> None:
    result = normalize_batch(
        _answering(), [NAME, "Kanüle"], templates, model="claude-sonnet-5", effort="medium"
    )

    assert result.readings is not None
    assert result.readings[1].category_code is None
