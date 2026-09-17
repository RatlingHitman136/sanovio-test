import uuid

from fastapi import APIRouter
from sqlalchemy import select

from service_kit.errors import NotFound
from supplier_hub.api.deps import CurrentPrincipal, CurrentUser, DbSession
from supplier_hub.models import ItemSearchProjection, Organization, ProductFamily, ProductVariant
from supplier_hub.models.organizations import OrganizationType
from supplier_hub.schemas.catalog import (
    FamilyView,
    SupplierView,
    VariantAttributesView,
    VariantView,
)

router = APIRouter(tags=["catalog"])


@router.get("/suppliers")
def list_suppliers(session: DbSession, _: CurrentPrincipal) -> list[SupplierView]:
    query = select(Organization).where(Organization.type == OrganizationType.SUPPLIER)
    return [
        SupplierView(id=org.id, name=org.name, country=org.country)
        for org in session.scalars(query.order_by(Organization.name))
    ]


@router.get("/catalog/variants")
def list_variants(
    session: DbSession,
    _: CurrentPrincipal,
    supplier: uuid.UUID | None = None,
    category: str | None = None,
    q: str | None = None,
) -> list[VariantView]:
    query = select(ItemSearchProjection).join(
        ProductVariant, ProductVariant.id == ItemSearchProjection.variant_id
    )
    if supplier is not None:
        query = query.where(ItemSearchProjection.supplier_id == supplier)
    if category is not None:
        query = query.where(ItemSearchProjection.category_code == category)
    if q:
        query = query.where(ItemSearchProjection.search_text.ilike(f"%{q.strip()}%"))
    return [_variant(row) for row in session.scalars(query.limit(100))]


@router.get("/catalog/families/{family_id}")
def get_family(family_id: uuid.UUID, session: DbSession, _: CurrentPrincipal) -> FamilyView:
    return _family(_load_family(session, family_id))


@router.get("/catalog/variants/{variant_id}/attributes")
def variant_attributes(
    variant_id: uuid.UUID, session: DbSession, _: CurrentPrincipal
) -> VariantAttributesView:
    """What the node's current-product preview is built from: values with their fact ids (§8.2)."""
    row = session.scalar(
        select(ItemSearchProjection).where(ItemSearchProjection.variant_id == variant_id)
    )
    if row is None:
        raise NotFound("variant not found")
    return VariantAttributesView(
        variant_id=variant_id,
        label=row.display_name,
        attributes={
            key: {"value": value, "fact_id": row.attribute_fact_ids.get(key)}
            for key, value in row.attributes.items()
        },
        identifiers=row.identifiers,
        additional_information=row.additional_attributes,
    )


@router.get("/supplier/catalog")
def supplier_catalog(session: DbSession, user: CurrentUser) -> list[FamilyView]:
    """A supplier sees its own catalog and nothing else."""
    query = select(ProductFamily).where(ProductFamily.supplier_id == user.org_id)
    return [_family(family) for family in session.scalars(query.order_by(ProductFamily.name))]


def _load_family(session: DbSession, family_id: uuid.UUID) -> ProductFamily:
    family = session.get(ProductFamily, family_id)
    if family is None:
        raise NotFound("family not found")
    return family


def _family(family: ProductFamily) -> FamilyView:
    return FamilyView(
        id=family.id,
        name=family.name,
        manufacturer=family.manufacturer,
        brand_name=family.brand_name,
        product_type=family.product_type,
        category_code=family.category_code,
        description=family.description,
        properties_text=family.properties_text,
        source_document=family.source_document,
        source_page=family.source_page,
        variants=[
            VariantView(
                variant_id=variant.id,
                article_no=variant.article_no,
                display_name=variant.label,
                category_code=family.category_code,
                supplier=family.supplier.name,
                attributes={},
            )
            for variant in family.variants
        ],
    )


def _variant(row: ItemSearchProjection) -> VariantView:
    return VariantView(
        variant_id=row.variant_id,
        article_no=row.variant.article_no,
        display_name=row.display_name,
        category_code=row.category_code,
        supplier=row.variant.family.supplier.name,
        attributes=row.attributes,
    )
