from datetime import UTC, datetime
from pathlib import Path

from hospital_node.core.settings import NodeSettings
from hospital_node.evals import extraction
from node_fixtures import fake_normalizer

NOW = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)


def test_scoring_counts_misses_and_extras() -> None:
    golden = {
        "3": {
            "category": "syringe_single_use",
            "attributes": {"nominal_volume_ml": 10, "connector": "LUER_LOCK", "sterile": True},
        }
    }
    found = {
        "3": (
            "syringe_single_use",
            {"nominal_volume_ml": 10.0, "connector": "LUER_LOCK", "sterile": False, "gauge": 21},
        )
    }

    result = extraction.score(found, golden, "rules")

    [article] = result.articles
    assert (article.correct, article.missed, article.extra) == (2, ["sterile"], ["gauge"])
    assert result.accuracy == 3 / 4  # the category counts as one fact


def test_rules_alone_miss_what_only_a_reader_knows(settings: NodeSettings, tmp_path: Path) -> None:
    result = extraction.run("rules", llm=None, settings=settings, workdir=tmp_path, now=NOW)

    assert len(result.articles) == 10
    missed = {a.internal_id: a.missed for a in result.articles if a.missed}
    # "Nitril" means latex-free and "Einmal" single use; no parser reads that.
    assert missed == {"1": ["latex_free"], "3": ["single_use"], "8": ["latex_free", "single_use"]}
    assert result.usage == []


def test_the_llm_run_is_scored_and_its_calls_counted(
    settings: NodeSettings, tmp_path: Path
) -> None:
    result = extraction.run(
        "llm", llm=fake_normalizer(), settings=settings, workdir=tmp_path, now=NOW
    )

    rules = extraction.run("rules", llm=None, settings=settings, workdir=tmp_path, now=NOW)
    assert result.accuracy > rules.accuracy
    assert [(u.model, u.calls) for u in result.usage] == [(settings.normalize_model, 1)]
