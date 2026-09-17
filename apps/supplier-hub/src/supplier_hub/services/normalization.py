"""Reads a family's printed text into facts, once per content change (§8.1, §13).

The core parsers already read the size tables; this adds what only prose states — the design,
the "nicht hergestellt mit Latex, DEHP und PVC" line, the ISO norm. Parsers win on conflicts.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.facts import SupplierSource
from llm_client import LLMClient
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.normalize_item import PROMPT_VERSION, ItemText, normalize_items
from supplier_hub.models import ProductFamily
from supplier_hub.models.catalog import CategorySource
from supplier_hub.services import catalog, llm_calls, projection, templates

log = logging.getLogger(__name__)


class NormalizationUnavailable(RuntimeError):
    """Families need the LLM, but no client is configured."""


def stale_families(session: Session) -> list[ProductFamily]:
    families = session.scalars(select(ProductFamily).order_by(ProductFamily.name))
    return [family for family in families if family.normalized_hash != family.content_hash]


def normalize(
    session: Session,
    families: Sequence[ProductFamily],
    *,
    llm: LLMClient | None,
    settings: HubSettings,
    now: datetime,
) -> None:
    """One call for the whole batch; the catalog rarely changes, so this runs at seed."""
    if not families:
        return
    known = templates.definitions(session)
    if settings.llm_mode == "anthropic" and llm is None:
        raise NormalizationUnavailable(
            "LLM_MODE=anthropic but no ANTHROPIC_API_KEY is set; use LLM_MODE=fake to seed offline"
        )
    readings = None
    if llm is not None:
        result = normalize_items(
            llm,
            [ItemText(name=family.name, text=_text_of(family)) for family in families],
            known,
            model=settings.normalize_item_model,
            effort=settings.normalize_item_effort,
        )
        call_ids = [llm_calls.record_call(session, record, now=now) for record in result.records]
        if result.readings is None:
            log.warning("normalize_item failed (%s); catalog facts only", result.records[-1].error)
        else:
            readings = list(zip(result.readings, [call_ids[-1]] * len(families), strict=False))

    for index, family in enumerate(families):
        template = known[family.category_code or ""]
        if readings is not None:
            reading, call_id = readings[index]
            if family.category_source is None and reading.category_code is not None:
                family.category_code = reading.category_code
                family.category_source = CategorySource.LLM_SUGGESTED
                family.category_set_at = now
                template = known[family.category_code]
            already = {fact.attribute_key for fact in catalog.family_facts(session, family.id)}
            for fact in reading.facts:
                # The catalog's own tables win; the model only fills what prose adds.
                if fact.attribute_key in already or fact.attribute_key not in template.keys:
                    continue
                catalog.add_fact(
                    session,
                    family_id=family.id,
                    key=fact.attribute_key,
                    value=fact.value,
                    raw=fact.quote,
                    now=now,
                    source=SupplierSource.EXTRACTION,
                    evidence_quote=fact.quote,
                    confidence=Decimal(str(round(fact.confidence, 2))),
                    llm_call_id=call_id,
                    model_id=settings.normalize_item_model,
                    prompt_version=PROMPT_VERSION,
                )
            family.normalized_hash = family.content_hash
        elif llm is None:
            # Nothing to wait for: the parsers already did their part.
            family.normalized_hash = family.content_hash
        projection.rebuild_family(session, family, template, now=now)
    session.flush()


def _text_of(family: ProductFamily) -> str:
    return " ".join(
        part for part in (family.product_type, family.description, family.properties_text) if part
    )
