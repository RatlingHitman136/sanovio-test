"""How well the node reads the 10 demo article names (§9: ≥90%, `rules` vs `llm` + parsers).

Each run seeds `demo_ksp` into a scratch database, exactly as `make seed` would, and compares
the resulting projections with the hand-labelled golden set.
"""

import math
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from hospital_node.core.db import Base
from hospital_node.core.settings import NodeSettings
from hospital_node.models import HospitalArticle
from hospital_node.services.seed import seed
from llm_client import LLMClient, ModelUsage, RecordingLLM, summarize
from service_kit.db import make_engine, make_session_factory
from service_kit.security import PasswordHasher

type Mode = Literal["rules", "llm"]
TARGET = 0.9


@dataclass(frozen=True)
class ArticleScore:
    internal_id: str
    category_ok: bool
    correct: int
    expected: int
    missed: list[str]
    extra: list[str]


@dataclass
class ExtractionScore:
    mode: Mode
    articles: list[ArticleScore]
    usage: list[ModelUsage] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        """Share of golden facts found, the category counting as one fact per article."""
        correct = sum(a.correct + a.category_ok for a in self.articles)
        expected = sum(a.expected + 1 for a in self.articles)
        return correct / expected

    @property
    def extras(self) -> int:
        return sum(len(a.extra) for a in self.articles)

    @property
    def passed(self) -> bool:
        return self.accuracy >= TARGET


def load_golden() -> dict[str, Any]:
    path = resources.files("hospital_node") / "evals" / "golden_extraction.yaml"
    golden: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return golden


def run(
    mode: Mode, *, llm: LLMClient | None, settings: NodeSettings, workdir: Path, now: datetime
) -> ExtractionScore:
    recording = None if llm is None else RecordingLLM(llm)
    scratch = settings.model_copy(
        update={"database_url": f"sqlite:///{workdir / f'eval-{mode}.db'}", "normalize_mode": mode}
    )
    engine = make_engine(scratch.database_url)
    Base.metadata.create_all(engine)
    try:
        with make_session_factory(engine).begin() as session:
            seed(
                session,
                "demo_ksp",
                password=secrets.token_urlsafe(16),
                hasher=PasswordHasher(),
                llm=recording,
                settings=scratch,
                now=now,
            )
            found = read_projections(session)
    finally:
        engine.dispose()
    result = score(found, load_golden(), mode)
    result.usage = summarize(recording.records if recording else [])
    return result


def read_projections(session: Session) -> dict[str, tuple[str | None, dict[str, Any]]]:
    """Per article: its category and the plain values of its projection."""
    found = {}
    for article in session.scalars(select(HospitalArticle)):
        projection = article.projection
        values = {} if projection is None else projection.attributes
        found[article.internal_id] = (
            article.category_code,
            {key: value.get("value") for key, value in values.items()},
        )
    return found


def score(
    found: dict[str, tuple[str | None, dict[str, Any]]], golden: dict[str, Any], mode: Mode
) -> ExtractionScore:
    articles = []
    for internal_id, truth in golden.items():
        category, values = found.get(internal_id, (None, {}))
        expected: dict[str, Any] = truth["attributes"]
        missed = [key for key, value in expected.items() if not _same(values.get(key), value)]
        articles.append(
            ArticleScore(
                internal_id=internal_id,
                category_ok=category == truth["category"],
                correct=len(expected) - len(missed),
                expected=len(expected),
                missed=missed,
                extra=sorted(set(values) - set(expected)),
            )
        )
    return ExtractionScore(mode, articles)


def _same(found: Any, expected: Any) -> bool:
    if isinstance(expected, bool) or isinstance(found, bool):
        return found is expected
    if isinstance(expected, int | float) and isinstance(found, int | float):
        return math.isclose(found, expected, rel_tol=1e-6)
    return str(found).upper() == str(expected).upper() if found is not None else False
