import uuid

from fastapi import APIRouter

from hospital_node.api.deps import Context, DbSession, Purchaser
from hospital_node.models.exchange import EgressKind
from hospital_node.schemas.exchange import RequirementRequest, RequirementResponse
from hospital_node.services import articles, egress_log, projection, template_sync
from service_kit.errors import Conflict

router = APIRouter(tags=["exchange"])


@router.post("/articles/{article_id}/requirement")
def issue_requirement(
    article_id: uuid.UUID,
    body: RequirementRequest,
    context: Context,
    session: DbSession,
    user: Purchaser,
) -> RequirementResponse:
    """Builds the requirement from the projection and records it before returning it (§16)."""
    article = articles.get(session, article_id)
    if article.projection is None or article.category_code is None:
        raise Conflict("NOT_NORMALIZED", "this article has no projection yet")
    template = template_sync.installed(session)[article.category_code]
    requirement = projection.issue_requirement(
        article,
        article.projection,
        template,
        context.settings,
        answered_question_ids=body.answered_question_ids,
    )
    row = egress_log.issue(
        session,
        kind=EgressKind.REQUIREMENT,
        user=user,
        content=requirement.model_dump(mode="json"),
        limits=egress_log.limits_for(EgressKind.REQUIREMENT, context.settings),
        now=context.clock(),
        article_id=article.id,
    )
    return RequirementResponse(requirement=requirement, egress_id=row.id)
