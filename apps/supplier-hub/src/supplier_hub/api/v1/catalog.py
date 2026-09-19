import uuid

from fastapi import APIRouter
from sqlalchemy import select

from equivalence_core.facts import ResolvedRecord, SupplierSource
from service_kit.errors import NotFound
from supplier_hub.api.deps import Context, CurrentPrincipal, CurrentUser, DbSession, Supplier
from supplier_hub.models import ItemSearchProjection, Organization, ProductFamily, ProductVariant
from supplier_hub.models.organizations import OrganizationType
from supplier_hub.schemas.catalog import (
    CatalogAttribute,
    CatalogEdit,
    CatalogValue,
    FamilyCreate,
    FamilyEdit,
    FamilyView,
    OwnFact,
    SupplierFamilyDetail,
    SupplierView,
    VariantAttributesView,
    VariantCreate,
    VariantValues,
    VariantView,
)
from supplier_hub.services import catalog, supplier_catalog, supplier_products
from supplier_hub.services.supplier_products import FamilyText, VariantRow

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
def own_catalog(session: DbSession, user: CurrentUser) -> list[FamilyView]:
    """A supplier sees its own catalog and nothing else."""
    return [_family(family) for family in catalog.families(session, supplier_id=user.org_id)]


@router.get("/supplier/catalog/families/{family_id}")
def supplier_family(
    family_id: uuid.UUID, session: DbSession, user: Supplier
) -> SupplierFamilyDetail:
    """The supplier's family: its own values, and each variant's with its scope (§9)."""
    return family_detail(session, supplier_catalog.family_view(session, user, family_id))


def family_detail(session: DbSession, view: supplier_catalog.FamilyView) -> SupplierFamilyDetail:
    """Also what an operator reads, without the edit buttons (§17.1)."""
    return SupplierFamilyDetail(
        id=view.family.id,
        name=view.family.name,
        manufacturer=view.family.manufacturer,
        brand_name=view.family.brand_name,
        product_type=view.family.product_type,
        description=view.family.description,
        properties_text=view.family.properties_text,
        category_code=view.family.category_code,
        reading=view.family.normalized_hash != view.family.content_hash,
        attributes=[
            CatalogAttribute(
                key=attribute.key,
                label=attribute.labels.en,
                type=attribute.type,
                unit=attribute.unit,
                options=list(attribute.options),
                criticality=attribute.criticality,
            )
            for attribute in view.template.attributes
        ],
        family_values=_values(view.family_record),
        family_unavailable=list(view.family_record.unavailable_attributes),
        variants=[
            VariantValues(
                variant_id=variant.id,
                article_no=variant.article_no,
                label=variant.label,
                is_active=variant.is_active,
                size_text=variant.source_row.get("Größe"),
                order_unit=variant.order_unit,
                units_per_order_unit=variant.units_per_order_unit,
                order_units_per_shipping_unit=variant.order_units_per_shipping_unit,
                values=_values(record),
                unavailable=list(record.unavailable_attributes),
            )
            for variant, record in view.variants
        ],
        own_facts=[
            OwnFact(
                fact_id=fact.id,
                attribute_key=fact.attribute_key,
                variant_id=fact.variant_id,
                value=fact.value,
                unavailable=fact.source == SupplierSource.UNAVAILABLE,
            )
            for fact in supplier_catalog.own_facts(session, view.family)
        ],
    )


@router.put("/supplier/catalog/facts")
def set_catalog_value(
    body: CatalogEdit, context: Context, session: DbSession, user: Supplier
) -> OwnFact:
    """Sets a value for the whole family, or overrides it for one variant."""
    fact = supplier_catalog.set_value(
        session,
        user,
        family_id=body.family_id,
        variant_id=body.variant_id,
        key=body.attribute_key,
        value=body.value,
        unavailable=body.unavailable,
        now=context.clock(),
    )
    return OwnFact(
        fact_id=fact.id,
        attribute_key=fact.attribute_key,
        variant_id=fact.variant_id,
        value=fact.value,
        unavailable=body.unavailable,
    )


@router.delete("/supplier/catalog/facts/{fact_id}", status_code=204)
def withdraw_catalog_value(
    fact_id: uuid.UUID, context: Context, session: DbSession, user: Supplier
) -> None:
    """Takes back one of the supplier's own values; what was there before shows again."""
    supplier_catalog.withdraw(session, user, fact_id, now=context.clock())


@router.post("/supplier/catalog/families")
def create_family(
    body: FamilyCreate, context: Context, session: DbSession, user: Supplier
) -> SupplierFamilyDetail:
    """A product line the supplier enters itself, read like a printed one (D59)."""
    text = FamilyText(**body.model_dump(exclude={"category_code"}))
    family = supplier_products.create_family(
        session, user, text, body.category_code, now=context.clock()
    )
    return family_detail(session, supplier_catalog.view_of(session, family))


@router.patch("/supplier/catalog/families/{family_id}")
def edit_family(
    family_id: uuid.UUID, body: FamilyEdit, context: Context, session: DbSession, user: Supplier
) -> SupplierFamilyDetail:
    """A changed text is read again; what the old text said no longer counts."""
    family = supplier_products.edit_family(
        session,
        user,
        family_id,
        text=FamilyText(**body.text.model_dump()) if body.text is not None else None,
        category_code=body.category_code,
        now=context.clock(),
    )
    return family_detail(session, supplier_catalog.view_of(session, family))


@router.post("/supplier/catalog/families/{family_id}/variants")
def add_variant(
    family_id: uuid.UUID,
    body: VariantCreate,
    context: Context,
    session: DbSession,
    user: Supplier,
) -> SupplierFamilyDetail:
    variant = supplier_products.add_variant(
        session, user, family_id, VariantRow(**body.model_dump()), now=context.clock()
    )
    return family_detail(session, supplier_catalog.view_of(session, variant.family))


@router.post("/supplier/catalog/variants/{variant_id}/retire")
def retire_variant(
    variant_id: uuid.UUID, context: Context, session: DbSession, user: Supplier
) -> SupplierFamilyDetail:
    """Out of search and new assessments; open assessments keep it."""
    return _set_active(variant_id, False, context, session, user)


@router.post("/supplier/catalog/variants/{variant_id}/reactivate")
def reactivate_variant(
    variant_id: uuid.UUID, context: Context, session: DbSession, user: Supplier
) -> SupplierFamilyDetail:
    return _set_active(variant_id, True, context, session, user)


def _set_active(
    variant_id: uuid.UUID, active: bool, context: Context, session: DbSession, user: Supplier
) -> SupplierFamilyDetail:
    variant = supplier_products.set_variant_active(
        session, user, variant_id, active=active, now=context.clock()
    )
    return family_detail(session, supplier_catalog.view_of(session, variant.family))


def _values(record: ResolvedRecord) -> dict[str, CatalogValue]:
    return {
        key: CatalogValue(
            value=resolved.value.model_dump(mode="json"),
            source=resolved.source,
            scope=resolved.scope,
            fact_id=resolved.fact_id,
        )
        for key, resolved in record.attributes.items()
    }


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
