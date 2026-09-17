"""Rebuilds an article's projection (N.6) from its active facts."""

from datetime import datetime

from sqlalchemy.orm import Session

from equivalence_core.exchange.requirement import AttributeOrigin, RequirementPayload
from equivalence_core.facts import HospitalSource, resolve_hospital
from equivalence_core.templates import TemplateDefinition
from hospital_node.core.settings import NodeSettings
from hospital_node.models import ArticleProjection, HospitalArticle
from hospital_node.services.facts import to_core
from hospital_node.services.requirement_builder import build_requirement, product_hints

ORIGIN = {
    HospitalSource.HOSPITAL_MASTER: AttributeOrigin.MASTER,
    HospitalSource.EXTRACTION: AttributeOrigin.EXTRACTED,
    HospitalSource.REFERENCE_ITEM: AttributeOrigin.REFERENCE,
    HospitalSource.PURCHASER_ANSWER: AttributeOrigin.PURCHASER,
}


def rebuild(
    session: Session,
    article: HospitalArticle,
    template: TemplateDefinition,
    *,
    settings: NodeSettings,
    now: datetime,
) -> ArticleProjection:
    record = resolve_hospital(to_core(article.facts), template)
    projection = article.projection or ArticleProjection(article_id=article.id)
    projection.category_code = template.code
    projection.definition_hash = template.definition_hash
    projection.attributes = {
        key: resolved.value.model_dump(mode="json") for key, resolved in record.attributes.items()
    }
    projection.attribute_origin = {
        key: ORIGIN[HospitalSource(resolved.source)] for key, resolved in record.attributes.items()
    }
    projection.attribute_fact_ids = {
        key: resolved.fact_id for key, resolved in record.attributes.items()
    }
    projection.identifiers = [entry.model_dump(mode="json") for entry in record.identifiers]
    projection.unknown_attributes = list(record.unknown_attributes)
    projection.unavailable_attributes = list(record.unavailable_attributes)
    projection.record_hash = record.record_hash()
    projection.updated_at = now
    # The hash of exactly what the requirement builder would issue now, so they cannot drift.
    projection.requirement_hash = issue_requirement(
        article, projection, template, settings
    ).requirement_hash()
    article.projection = projection
    session.flush()
    return projection


def issue_requirement(
    article: HospitalArticle,
    projection: ArticleProjection,
    template: TemplateDefinition,
    settings: NodeSettings,
    answered_question_ids: tuple[str, ...] = (),
) -> RequirementPayload:
    hints = (
        product_hints(article.brand, projection.identifiers)
        if settings.share_product_hints
        else None
    )
    return build_requirement(
        projection,
        article_ref=article.article_ref,
        template=template,
        deny=settings.egress_deny_attributes,
        hints=hints,
        answered_question_ids=answered_question_ids,
    )
