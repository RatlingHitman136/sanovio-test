"""The eval harness itself, run against the scripted fake: it scores, it does not judge models."""

from datetime import UTC, datetime
from pathlib import Path

from supplier_hub.core.settings import HubSettings
from supplier_hub.evals import answers, load, verdicts
from supplier_hub.llm.fakes import fake_llm

NOW = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)


def test_every_golden_case_runs_and_is_scored(settings: HubSettings, tmp_path: Path) -> None:
    scored = verdicts.run(llm=fake_llm(), settings=settings, workdir=tmp_path, now=NOW)

    assert [c.id for c in scored.cases] == [c["id"] for c in load("golden_verdicts.jsonl")]
    # The rule-based fake calls any two stopper descriptions a match; a real judge must not.
    assert [c.id for c in scored.cases if not c.verdict_ok] == ["injekt_stopper_latex"]
    assert scored.gap_recall == 1.0
    # Four of five model-decided judgments are right; the fake's latex stopper is the miss.
    assert scored.judge_accuracy == 4 / 5
    assert scored.passed
    assert {u.model for u in scored.usage} == {settings.judge_model, settings.compare_text_model}


def test_supplier_answers_of_one_case_stay_in_that_case(
    settings: HubSettings, tmp_path: Path
) -> None:
    scored = verdicts.run(llm=fake_llm(), settings=settings, workdir=tmp_path, now=NOW)

    by_id = {c.id: c for c in scored.cases}
    # plastipak_answered wrote BD's answers; the catalog-only case after it never sees them.
    assert by_id["plastipak_catalog_only"].verdict == "INSUFFICIENT_DATA"
    assert by_id["plastipak_answered"].verdict == "EQUIVALENT_WITH_DEVIATIONS"


def test_answer_extraction_is_compared_as_typed_values(settings: HubSettings) -> None:
    scored = answers.run(llm=fake_llm(), settings=settings)

    assert len(scored.answers) == len(load("golden_extraction.jsonl"))
    dehp = scored.answers[0]
    assert dehp.expected == {"type": "bool", "value": True}
    assert dehp.ok
    unclear = next(a for a in scored.answers if a.attribute_key == "safety_mechanism")
    assert (unclear.expected, unclear.found) == (None, None)
    assert {u.model for u in scored.usage} == {settings.extract_answer_model}
