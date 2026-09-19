"""Round-1 verdicts on labelled article/variant pairs (§9: ≥85% right, every critical gap asked).

The catalog comes from the scripted readings, so only the judge's part varies between runs.
Each case runs on its own copy of one seeded scratch database: supplier answers written for
one case never leak into the next.
"""

import secrets
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from equivalence_core.facts import SupplierSource
from equivalence_core.ids import new_article_ref, new_subject_id
from equivalence_core.templates import TemplateDefinition
from llm_client import LLMClient, ModelUsage, RecordingLLM, summarize
from service_kit.db import make_engine, make_session_factory
from service_kit.security import PasswordHasher
from supplier_hub.core.db import Base
from supplier_hub.core.settings import HubSettings
from supplier_hub.evals import load
from supplier_hub.jobs import handlers
from supplier_hub.jobs.worker import run_pending
from supplier_hub.llm.fakes import fake_llm
from supplier_hub.llm.values import PlainValue, typed_value
from supplier_hub.models import Assessment, Organization, ProductVariant
from supplier_hub.services import assessment, catalog, projection, templates
from supplier_hub.services.seed import seed

VERDICT_TARGET = 0.85
GAP_TARGET = 1.0


@dataclass(frozen=True)
class CaseResult:
    id: str
    expected_verdict: str
    verdict: str
    critical_gaps: list[str]
    asked: list[str]
    expected_judgments: dict[str, str]
    judgments: dict[str, str]

    @property
    def verdict_ok(self) -> bool:
        return self.verdict == self.expected_verdict


@dataclass
class VerdictScore:
    cases: list[CaseResult]
    usage: list[ModelUsage] = field(default_factory=list)

    @property
    def verdict_accuracy(self) -> float:
        return sum(c.verdict_ok for c in self.cases) / len(self.cases)

    @property
    def gap_recall(self) -> float:
        expected = sum(len(c.critical_gaps) for c in self.cases)
        asked = sum(len(set(c.critical_gaps) & set(c.asked)) for c in self.cases)
        return asked / expected if expected else 1.0

    @property
    def judge_accuracy(self) -> float | None:
        pairs = [
            (c.judgments.get(key), status)
            for c in self.cases
            for key, status in c.expected_judgments.items()
        ]
        return sum(found == status for found, status in pairs) / len(pairs) if pairs else None

    @property
    def passed(self) -> bool:
        return self.verdict_accuracy >= VERDICT_TARGET and self.gap_recall >= GAP_TARGET


def run(*, llm: LLMClient, settings: HubSettings, workdir: Path, now: datetime) -> VerdictScore:
    seeded = workdir / "seeded.db"
    _seed(seeded, settings, now)
    recording = RecordingLLM(llm)
    results = []
    for case in load("golden_verdicts.jsonl"):
        copy = workdir / f"{case['id']}.db"
        shutil.copy(seeded, copy)
        scratch = settings.model_copy(update={"database_url": f"sqlite:///{copy}"})
        engine = make_engine(scratch.database_url)
        try:
            results.append(_run_case(make_session_factory(engine), case, recording, scratch, now))
        finally:
            engine.dispose()
    return VerdictScore(results, summarize(recording.records))


def _seed(path: Path, settings: HubSettings, now: datetime) -> None:
    engine = make_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    try:
        with make_session_factory(engine).begin() as session:
            seed(
                session,
                password=secrets.token_urlsafe(16),
                hasher=PasswordHasher(),
                llm=fake_llm(),
                settings=settings,
                now=now,
            )
    finally:
        engine.dispose()


def _run_case(
    factory: sessionmaker[Session],
    case: dict[str, Any],
    llm: LLMClient,
    settings: HubSettings,
    now: datetime,
) -> CaseResult:
    with factory.begin() as session:
        template = templates.definition(session, case["template"])
        variant = session.scalar(
            select(ProductVariant).where(ProductVariant.article_no == case["article_no"])
        )
        assert variant is not None, case["article_no"]
        for key, raw in case["supplier_facts"].items():
            catalog.add_fact(
                session,
                key=key,
                value=_typed(template, key, raw),
                raw=str(raw),
                now=now,
                family_id=variant.family_id,
                source=SupplierSource.SUPPLIER_ANSWER,
            )
        projection.rebuild_family(session, variant.family, template, now=now)
        tenant = session.scalar(select(Organization).where(Organization.code == "ten_ksp"))
        assert tenant is not None
        principal = assessment.principal_for_subject(session, tenant.id, new_subject_id(), now=now)
        body = _requirement(template, case["requirement"])
        assessment_id = assessment.create(
            session, principal, body, variant.id, settings=settings, now=now
        ).id

    run_pending(
        factory,
        handlers.build(llm=llm, settings=settings),
        clock=lambda: now,
        on_give_up=assessment.give_up,
    )

    with factory() as session:
        found = session.get(Assessment, assessment_id)
        assert found is not None and found.rounds, case["id"]
        first = found.rounds[0]
        judgments = {j["attribute_key"]: j["status"] for j in first.attribute_judgments}
        return CaseResult(
            id=case["id"],
            expected_verdict=case["expected_verdict"],
            verdict=first.rule_verdict,
            critical_gaps=case["critical_gaps"],
            asked=sorted({q.attribute_key for q in found.questions if q.attribute_key}),
            expected_judgments=case["expected_judgments"],
            judgments={key: judgments.get(key, "-") for key in case["expected_judgments"]},
        )


def _requirement(template: TemplateDefinition, values: dict[str, PlainValue]) -> dict[str, Any]:
    """The requirement a node would send for these values (§16), all set by the purchaser."""
    attributes = {key: _typed(template, key, raw) for key, raw in values.items()}
    return {
        "article_ref": new_article_ref(),
        "template_code": template.code,
        "attributes": {key: value.model_dump(mode="json") for key, value in attributes.items()},
        "attribute_origin": {key: "PURCHASER" for key in attributes},
        "unknown_attributes": [key for key in template.keys if key not in attributes],
    }


def _typed(template: TemplateDefinition, key: str, raw: PlainValue) -> Any:
    value = typed_value(template.attribute(key), raw)
    if value is None:
        raise ValueError(f"golden value {raw!r} does not fit {template.code}.{key}")
    return value
