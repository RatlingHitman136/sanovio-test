"""Category templates: how each category compares its attributes (§7.2, D52)."""

from fastapi import APIRouter

from supplier_hub.api.deps import Context, DbSession, Operator
from supplier_hub.api.v1.templates import template_view
from supplier_hub.models.audit import AuditAction
from supplier_hub.schemas.admin import TemplateEditBody
from supplier_hub.schemas.templates import TemplateView
from supplier_hub.services import operator_audit, templates
from supplier_hub.services.templates import TemplateEdit

router = APIRouter()


@router.patch("/templates/{code}")
def edit_template(
    code: str, body: TemplateEditBody, context: Context, session: DbSession, operator: Operator
) -> TemplateView:
    """A new definition hash; every family of the category is re-projected, and nodes pick
    the change up at their next sync."""
    templates.edit(
        session,
        code,
        TemplateEdit(set=body.set, add=body.add, remove=body.remove),
        now=context.clock(),
        change_note=body.change_note,
        updated_by=operator.id,
    )
    operator_audit.record(
        session,
        operator,
        AuditAction.TEMPLATE_EDITED,
        target_type="template",
        target_id=code,
        now=context.clock(),
        data=body.model_dump(mode="json"),
    )
    return template_view(session, templates.row_for(session, code))
