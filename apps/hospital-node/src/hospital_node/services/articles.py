"""Hospital articles: ingestion of master records, lookup, category and corrections (§8.1)."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from equivalence_core.facts import HospitalSource
from equivalence_core.identifiers import (
    IdentifierScheme,
    checksum_valid,
    data_quality_issues,
    normalize_identifier,
)
from equivalence_core.ids import new_article_ref
from equivalence_core.templates import GENERIC_CODE, AttributeDefinition
from equivalence_core.validation import InvalidValue, validate_value
from equivalence_core.values import EnumValue, IdentifierValue, NumberValue, TypedValue
from hospital_node.core.settings import NodeSettings
from hospital_node.models import HospitalArticle, User
from hospital_node.models.articles import CategorySource
from hospital_node.services import normalization, projection
from hospital_node.services.errors import NotFound, Unprocessable
from hospital_node.services.facts import IDENTIFIER_KEYS, active_facts, add_fact, typed_value
from hospital_node.services.template_sync import Templates

# Column names of the client's article list (sample-challenge-v01, Tabelle3).
_IDENTIFIER_COLUMNS = {
    "GTIN": IdentifierScheme.GTIN,
    "EAN": IdentifierScheme.EAN,
    "Artikelnummer": IdentifierScheme.MANUFACTURER_REF,
}
_SEARCH_LIMIT = 50


def ingest(
    session: Session, raw: Mapping[str, str], *, templates: Templates, now: datetime
) -> HospitalArticle:
    """Stores one master record exactly as received and turns its master data into facts.
    Normalization of the name happens afterwards, for all ingested articles at once."""
    article = HospitalArticle(
        internal_id=raw["internal_id"],
        article_ref=new_article_ref(),
        name=raw["Artikelbezeichnung"],
        brand=raw.get("Marke") or None,
        annual_quantity=_integer(raw.get("Jahresmenge")),
        order_unit=raw.get("Bestellmengeneinheit") or None,
        base_units_per_order_unit=_integer(raw.get("Basismengeneinheiten pro BME")),
        base_unit=raw.get("Basismengeneinheit") or None,
        target_net_price=_decimal(raw.get("Netto-Zielpreis")),
        currency=raw.get("Währung") or None,
        raw=dict(raw),
        data_quality_issues=[],
    )
    article.content_hash = normalization.content_hash(article)
    session.add(article)
    generic = templates[GENERIC_CODE]
    master: list[tuple[str, TypedValue, str]] = []
    if mdr_class := raw.get("MDR-Klasse"):
        master.append(("mdr_class", EnumValue(value=mdr_class), mdr_class))
    if article.base_units_per_order_unit is not None:
        units = NumberValue(value=article.base_units_per_order_unit, unit="pcs")
        master.append(("units_per_order_unit", units, str(article.base_units_per_order_unit)))
    for key, value, raw_value in master:
        checked = validate_value(generic.attribute(key), value)
        _add_master(session, article, key, checked, raw_value, now)
    for column, scheme in _IDENTIFIER_COLUMNS.items():
        if written := raw.get(column):
            _add_master(
                session, article, scheme.lower(), _identifier(scheme, written), written, now
            )
    refresh_identifier_issues(article)
    return article


def search(
    session: Session, *, text: str | None = None, article_refs: Sequence[str] = ()
) -> list[HospitalArticle]:
    query = select(HospitalArticle).order_by(HospitalArticle.internal_id).limit(_SEARCH_LIMIT)
    if article_refs:
        query = query.where(HospitalArticle.article_ref.in_(article_refs))
    if text:
        pattern = f"%{text.strip()}%"
        query = query.where(
            or_(HospitalArticle.name.ilike(pattern), HospitalArticle.internal_id == text.strip())
        )
    return list(session.scalars(query))


def get(session: Session, article_id: uuid.UUID) -> HospitalArticle:
    article = session.get(HospitalArticle, article_id)
    if article is None:
        raise NotFound("article not found")
    return article


def set_category(
    session: Session,
    article: HospitalArticle,
    code: str,
    *,
    user: User,
    templates: Templates,
    settings: NodeSettings,
    now: datetime,
) -> None:
    if code not in templates:
        raise Unprocessable(f"no installed template for category {code!r}")
    article.category_code = code
    article.category_source = CategorySource.PURCHASER
    article.category_set_by = user.id
    article.category_set_at = now
    # The parsers re-read the name for the new category's attributes; no LLM call (D56).
    normalization.apply_rules(session, article, templates[code], settings=settings, now=now)


def set_fact(
    session: Session,
    article: HospitalArticle,
    key: str,
    value: TypedValue | None,
    *,
    hub_question_id: str | None,
    user: User,
    templates: Templates,
    settings: NodeSettings,
    now: datetime,
) -> None:
    """A purchaser's correction or answer; `value=None` means "cannot provide"."""
    template = templates[article.category_code or GENERIC_CODE]
    if key in IDENTIFIER_KEYS:
        stored: TypedValue | None = _purchaser_identifier(key, value)
    elif key in template.keys:
        stored = None if value is None else _checked(template.attribute(key), value)
    else:
        raise Unprocessable(f"{key!r} is neither an attribute of {template.code} nor an identifier")
    add_fact(
        session,
        article,
        key=key,
        value=stored,
        source=HospitalSource.UNAVAILABLE if stored is None else HospitalSource.PURCHASER_ANSWER,
        now=now,
        created_by=user.id,
        hub_question_id=hub_question_id,
    )
    if key in IDENTIFIER_KEYS:
        refresh_identifier_issues(article)
    projection.rebuild(session, article, template, settings=settings, now=now)


def refresh_identifier_issues(article: HospitalArticle) -> None:
    """Recomputes the identifier problems; for each scheme the purchaser's value wins."""
    current: dict[IdentifierScheme, str] = {}
    for fact in sorted(
        active_facts(article), key=lambda f: f.source == HospitalSource.PURCHASER_ANSWER
    ):
        if fact.value is not None and fact.attribute_key in IDENTIFIER_KEYS:
            identifier = typed_value(fact.value)
            if isinstance(identifier, IdentifierValue):
                current[identifier.scheme] = identifier.value
    kept = [i for i in article.data_quality_issues if i in normalization.NAME_ISSUES]
    article.data_quality_issues = [str(i) for i in data_quality_issues(current)] + kept


def _purchaser_identifier(key: str, value: TypedValue | None) -> IdentifierValue:
    scheme = IDENTIFIER_KEYS[key]
    if not isinstance(value, IdentifierValue) or value.scheme != scheme:
        raise Unprocessable(f"{key} expects an identifier value with scheme {scheme}")
    return _identifier(scheme, value.value)


def _identifier(scheme: IdentifierScheme, written: str) -> IdentifierValue:
    # checksum_valid is always computed here, never taken from the caller.
    value = normalize_identifier(written)
    return IdentifierValue(scheme=scheme, value=value, checksum_valid=checksum_valid(scheme, value))


def _checked(definition: AttributeDefinition, value: TypedValue) -> TypedValue:
    try:
        return validate_value(definition, value)
    except InvalidValue as exc:
        raise Unprocessable(str(exc)) from exc


def _add_master(
    session: Session,
    article: HospitalArticle,
    key: str,
    value: TypedValue,
    raw_value: str,
    now: datetime,
) -> None:
    add_fact(
        session,
        article,
        key=key,
        value=value,
        source=HospitalSource.HOSPITAL_MASTER,
        now=now,
        raw_value=raw_value,
    )


def _integer(text: str | None) -> int | None:
    return int(text) if text and text.strip().isdigit() else None


def _decimal(text: str | None) -> Decimal | None:
    try:
        return Decimal(text) if text else None
    except InvalidOperation:
        return None
