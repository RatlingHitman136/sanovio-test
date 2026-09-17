import uuid

from fastapi import APIRouter

from hospital_node.api.deps import AnyNodeUser, Context, DbSession
from hospital_node.api.v1.articles import detail
from hospital_node.schemas.articles import ArticleDetail
from hospital_node.schemas.reference import (
    ConflictView,
    FillView,
    PreviewView,
    ReferenceInput,
    ReferenceSet,
)
from hospital_node.services import articles, reference_link, template_sync
from hospital_node.services.reference_link import Reported

router = APIRouter(prefix="/articles/{article_id}/reference", tags=["current product"])


@router.post("/preview")
def preview(
    article_id: uuid.UUID, body: ReferenceInput, session: DbSession, _: AnyNodeUser
) -> PreviewView:
    article = articles.get(session, article_id)
    template = template_sync.installed(session)[article.category_code or ""]
    plan = reference_link.preview(article, template, _reported(body))
    return PreviewView(
        fills=[FillView(key=key, value=fill.value) for key, fill in plan.fills.items()],
        conflicts=[
            ConflictView(key=key, ours=c.ours, ours_source=c.ours_source, theirs=c.theirs)
            for key, c in plan.conflicts.items()
        ],
        kept_purchaser=plan.kept_purchaser,
        identifiers_info=plan.identifiers,
        ignored=plan.ignored,
    )


@router.put("")
def set_reference(
    article_id: uuid.UUID,
    body: ReferenceSet,
    context: Context,
    session: DbSession,
    user: AnyNodeUser,
) -> ArticleDetail:
    article = articles.get(session, article_id)
    reference_link.link(
        session,
        article,
        template_sync.installed(session)[article.category_code or ""],
        variant_id=body.variant_id,
        label=body.label,
        reported=_reported(body),
        choices=body.conflict_choices,
        user=user,
        settings=context.settings,
        now=context.clock(),
    )
    return detail(article)


@router.delete("")
def remove_reference(
    article_id: uuid.UUID, context: Context, session: DbSession, _: AnyNodeUser
) -> ArticleDetail:
    article = articles.get(session, article_id)
    reference_link.unlink(
        session,
        article,
        template_sync.installed(session)[article.category_code or ""],
        settings=context.settings,
        now=context.clock(),
    )
    return detail(article)


def _reported(body: ReferenceInput) -> dict[str, Reported]:
    return {key: Reported(item.value, item.fact_id) for key, item in body.attributes.items()}
