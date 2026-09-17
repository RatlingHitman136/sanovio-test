import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from equivalence_core.facts import HospitalSource
from hospital_node.api.deps import AnyNodeUser, Context, DbSession
from hospital_node.models import HospitalArticle
from hospital_node.schemas.articles import (
    ArticleDetail,
    ArticleSummary,
    AttributeView,
    CategoryUpdate,
    FactUpdate,
    IdentifierView,
    ReferenceView,
    summary_fields,
)
from hospital_node.services import articles, template_sync
from hospital_node.services.facts import typed_value

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("")
def list_articles(
    session: DbSession,
    _: AnyNodeUser,
    q: str | None = None,
    article_ref: Annotated[str | None, Query(description="Comma-separated article_refs")] = None,
) -> list[ArticleSummary]:
    refs = [ref.strip() for ref in article_ref.split(",") if ref.strip()] if article_ref else []
    found = articles.search(session, text=q, article_refs=refs)
    return [ArticleSummary(**summary_fields(article)) for article in found]


@router.get("/{article_id}")
def get_article(article_id: uuid.UUID, session: DbSession, _: AnyNodeUser) -> ArticleDetail:
    return detail(articles.get(session, article_id))


@router.put("/{article_id}/category")
def set_category(
    article_id: uuid.UUID,
    body: CategoryUpdate,
    context: Context,
    session: DbSession,
    user: AnyNodeUser,
) -> ArticleDetail:
    article = articles.get(session, article_id)
    articles.set_category(
        session,
        article,
        body.category_code,
        user=user,
        templates=template_sync.installed(session),
        settings=context.settings,
        now=context.clock(),
    )
    return detail(article)


@router.put("/{article_id}/facts/{attribute_key}")
def set_fact(
    article_id: uuid.UUID,
    attribute_key: str,
    body: FactUpdate,
    context: Context,
    session: DbSession,
    user: AnyNodeUser,
) -> ArticleDetail:
    article = articles.get(session, article_id)
    articles.set_fact(
        session,
        article,
        attribute_key,
        body.value,
        hub_question_id=body.hub_question_id,
        user=user,
        templates=template_sync.installed(session),
        settings=context.settings,
        now=context.clock(),
    )
    return detail(article)


def detail(article: HospitalArticle) -> ArticleDetail:
    projection = article.projection
    facts = {str(fact.id): fact for fact in article.facts}
    attributes = []
    if projection is not None:
        for key, fact_id in projection.attribute_fact_ids.items():
            fact = facts[fact_id]
            attributes.append(
                AttributeView(
                    key=key,
                    value=typed_value(projection.attributes[key]),
                    source=HospitalSource(fact.source),
                    method=fact.method,
                    quote=fact.raw_value,
                    fact_id=fact.id,
                )
            )
    reference = (
        ReferenceView(
            variant_id=article.reference_hub_variant_id,
            label=article.reference_label,
            linked_at=article.reference_linked_at,
        )
        if article.reference_hub_variant_id
        else None
    )
    return ArticleDetail(
        **summary_fields(article),
        annual_quantity=article.annual_quantity,
        order_unit=article.order_unit,
        base_units_per_order_unit=article.base_units_per_order_unit,
        base_unit=article.base_unit,
        target_net_price=None
        if article.target_net_price is None
        else str(article.target_net_price),
        currency=article.currency,
        category_set_at=article.category_set_at,
        attributes=attributes,
        unknown_attributes=projection.unknown_attributes if projection else [],
        unavailable_attributes=projection.unavailable_attributes if projection else [],
        identifiers=[IdentifierView(**entry) for entry in projection.identifiers]
        if projection
        else [],
        reference=reference,
        requirement_hash=projection.requirement_hash if projection else None,
    )
