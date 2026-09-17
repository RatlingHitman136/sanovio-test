"""Reads article names into facts and a category, once per content change (D42, D56).

The parsers always run and win on every attribute they read (D8). In `llm` mode one
`normalize_article` call per batch adds what the parsers cannot read, plus a category
suggestion. A restart with unchanged articles, and every API request, makes no call.
"""

import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from importlib.metadata import version
from itertools import batched

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.facts import HospitalSource
from equivalence_core.hashing import sha256_hex
from equivalence_core.parsers import extract_attributes
from equivalence_core.quality import DataQualityIssue
from equivalence_core.templates import TemplateDefinition, suggest_category
from equivalence_core.values import AttributeValue
from hospital_node.core.settings import NodeSettings
from hospital_node.llm.normalize_article import PROMPT_VERSION, ArticleReading, normalize_batch
from hospital_node.models import ArticleFact, HospitalArticle
from hospital_node.models.articles import CategorySource, FactMethod
from hospital_node.services import projection
from hospital_node.services.facts import active_facts, add_fact, retract
from hospital_node.services.llm_calls import record_call
from hospital_node.services.template_sync import Templates
from llm_client import LLMClient

log = logging.getLogger(__name__)

PARSER_VERSION = f"equivalence-core {version('equivalence-core')}"
NAME_ISSUES = frozenset({DataQualityIssue.GAUGE_DIAMETER_MISMATCH})


class NormalizationUnavailable(RuntimeError):
    """Articles need the LLM, but no client is configured."""


@dataclass(frozen=True)
class _LlmReading:
    reading: ArticleReading
    call_id: uuid.UUID


def content_hash(article: HospitalArticle) -> str:
    # `raw` is the master record exactly as received, so it covers every source field.
    return sha256_hex(article.raw)


def stale_articles(session: Session) -> list[HospitalArticle]:
    articles = session.scalars(select(HospitalArticle).order_by(HospitalArticle.internal_id))
    return [article for article in articles if article.normalized_hash != article.content_hash]


def normalize_stale(
    session: Session,
    *,
    templates: Templates,
    llm: LLMClient | None,
    settings: NodeSettings,
    now: datetime,
) -> int:
    """The startup pass; returns how many articles had changed."""
    stale = stale_articles(session)
    if stale:
        normalize(session, stale, templates=templates, llm=llm, settings=settings, now=now)
    return len(stale)


def normalize(
    session: Session,
    articles: Sequence[HospitalArticle],
    *,
    templates: Templates,
    llm: LLMClient | None,
    settings: NodeSettings,
    now: datetime,
) -> None:
    use_llm = settings.normalize_mode == "llm"
    if use_llm and llm is None:
        raise NormalizationUnavailable(
            f"{len(articles)} article(s) need normalization, but NORMALIZE_MODE=llm and no "
            "ANTHROPIC_API_KEY is set. Set the hospital's key, or use NORMALIZE_MODE=rules."
        )
    for batch in batched(articles, settings.normalize_batch_size, strict=False):
        readings = (
            _read_with_llm(session, batch, templates, llm, settings, now)
            if llm and use_llm
            else None
        )
        for index, article in enumerate(batch):
            reading = readings[index] if readings is not None else None
            _normalize_one(session, article, reading, templates, settings, now)
            # After a failed call the article stays stale, so the next startup retries it.
            if readings is not None or not use_llm:
                article.normalized_hash = article.content_hash


def apply_rules(
    session: Session,
    article: HospitalArticle,
    template: TemplateDefinition,
    *,
    settings: NodeSettings,
    now: datetime,
) -> None:
    """Re-reads the name with the parsers only, e.g. after the purchaser changed the category.
    Facts from an earlier LLM pass stay; the resolver ignores those outside the template."""
    retract(_extractions(article, FactMethod.RULES), now=now)
    _write_rules(session, article, template, now)
    projection.rebuild(session, article, template, settings=settings, now=now)


def _read_with_llm(
    session: Session,
    batch: Sequence[HospitalArticle],
    templates: Templates,
    llm: LLMClient,
    settings: NodeSettings,
    now: datetime,
) -> list[_LlmReading] | None:
    result = normalize_batch(
        llm,
        [article.name for article in batch],
        templates,
        model=settings.normalize_model,
        effort=settings.normalize_effort,
    )
    call_ids = [record_call(session, record, now=now) for record in result.records]
    if result.readings is None:
        log.warning("normalize_article failed (%s); rules only", result.records[-1].error)
        return None
    # The last call is the one whose answer was accepted.
    return [_LlmReading(reading, call_ids[-1]) for reading in result.readings]


def _normalize_one(
    session: Session,
    article: HospitalArticle,
    llm_reading: _LlmReading | None,
    templates: Templates,
    settings: NodeSettings,
    now: datetime,
) -> None:
    suggested = llm_reading.reading.category_code if llm_reading else None
    if article.category_source != CategorySource.PURCHASER:
        article.category_code = suggested or suggest_category(article.name, templates)
        article.category_source = (
            CategorySource.LLM_SUGGESTED if suggested else CategorySource.RULES
        )
        article.category_set_by = None
        article.category_set_at = now
    template = templates[article.category_code or ""]

    retract(_extractions(article), now=now)
    found = _write_rules(session, article, template, now)
    if llm_reading is not None:
        for fact in llm_reading.reading.facts:
            # The parsers are authoritative for whatever they read; the model only fills gaps.
            if fact.attribute_key in found or fact.attribute_key not in template.keys:
                continue
            _add_extraction(
                session,
                article,
                fact.attribute_key,
                fact.value,
                fact.quote,
                FactMethod.LLM,
                now,
                llm_call_id=llm_reading.call_id,
                model_id=settings.normalize_model,
                prompt_version=PROMPT_VERSION,
                confidence=Decimal(str(round(fact.confidence, 2))),
            )
    projection.rebuild(session, article, template, settings=settings, now=now)


def _write_rules(
    session: Session, article: HospitalArticle, template: TemplateDefinition, now: datetime
) -> set[str]:
    reading = extract_attributes(article.name, template)
    for extraction in reading.extractions:
        _add_extraction(
            session,
            article,
            extraction.attribute_key,
            extraction.value,
            extraction.quote,
            FactMethod.RULES,
            now,
            parser_version=PARSER_VERSION,
        )
    identifier_issues = [i for i in article.data_quality_issues if i not in NAME_ISSUES]
    article.data_quality_issues = identifier_issues + [str(i) for i in reading.issues]
    return {extraction.attribute_key for extraction in reading.extractions}


def _add_extraction(
    session: Session,
    article: HospitalArticle,
    key: str,
    value: AttributeValue,
    quote: str,
    method: FactMethod,
    now: datetime,
    **provenance: object,
) -> None:
    add_fact(
        session,
        article,
        key=key,
        value=value,
        source=HospitalSource.EXTRACTION,
        now=now,
        method=method,
        raw_value=quote,
        evidence_quote=article.name,
        **provenance,
    )


def _extractions(
    article: HospitalArticle, method: FactMethod | None = None
) -> Iterable[ArticleFact]:
    return [
        fact
        for fact in active_facts(article)
        if fact.source == HospitalSource.EXTRACTION and method in (None, fact.method)
    ]
