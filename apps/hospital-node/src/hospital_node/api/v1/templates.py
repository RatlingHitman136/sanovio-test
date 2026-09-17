from fastapi import APIRouter

from hospital_node.api.deps import AnyNodeUser, Context, DbSession
from hospital_node.models import InstalledTemplate
from hospital_node.schemas.templates import InstalledTemplateView, TemplateInstall
from hospital_node.services import template_sync

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
def list_templates(session: DbSession, _: AnyNodeUser) -> list[InstalledTemplateView]:
    return [_view(row) for row in template_sync.rows(session)]


@router.put("")
def install_template(
    body: TemplateInstall, context: Context, session: DbSession, user: AnyNodeUser
) -> InstalledTemplateView:
    row = template_sync.install(
        session,
        body.definition,
        user_id=user.id,
        settings=context.settings,
        now=context.clock(),
        hub_updated_at=body.updated_at,
    )
    return _view(row)


def _view(row: InstalledTemplate) -> InstalledTemplateView:
    return InstalledTemplateView(
        code=row.code,
        definition=row.definition,
        definition_hash=row.definition_hash,
        updated_at=row.hub_updated_at,
        installed_at=row.installed_at,
    )
