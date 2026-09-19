from fastapi import APIRouter

from supplier_hub.api.deps import DbSession, Token
from supplier_hub.models import CategoryTemplate
from supplier_hub.schemas.templates import AttributeView, TemplateView
from supplier_hub.services import attribute_registry, templates

router = APIRouter(tags=["registry"])


@router.get("/templates")
def list_templates(session: DbSession, _: Token) -> list[TemplateView]:
    """Every current definition; a node installs these as its own copies (D52)."""
    return [template_view(session, row) for row in templates.rows(session)]


@router.get("/templates/{code}")
def get_template(code: str, session: DbSession, _: Token) -> TemplateView:
    return template_view(session, templates.row_for(session, code))


@router.get("/attributes")
def list_attributes(
    session: DbSession, _: Token, category: str | None = None, status: str | None = None
) -> list[AttributeView]:
    """The registry itself, including attributes that are only provisional (§7.2)."""
    keys = None
    if category is not None:
        keys = [entry["key"] for entry in templates.row_for(session, category).attributes]
    return [
        AttributeView(
            key=row.key,
            kind=row.kind,
            value_type=row.value_type,
            unit=row.unit,
            options=row.options,
            labels=row.labels,
            status=row.status,
            origin=row.origin,
        )
        for row in attribute_registry.definitions(session, status=status, keys=keys)
    ]


def template_view(session: DbSession, row: CategoryTemplate) -> TemplateView:
    return TemplateView(
        code=row.code,
        definition=templates.definition(session, row.code).model_dump(mode="json"),
        definition_hash=row.definition_hash,
        change_note=row.change_note,
        updated_at=row.updated_at,
    )
