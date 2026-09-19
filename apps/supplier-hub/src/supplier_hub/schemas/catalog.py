import uuid
from typing import Any

from pydantic import BaseModel, Field

from equivalence_core.values import TypedValue


class SupplierView(BaseModel):
    id: uuid.UUID
    name: str
    country: str | None


class VariantView(BaseModel):
    variant_id: uuid.UUID
    article_no: str
    display_name: str
    category_code: str | None
    supplier: str
    attributes: dict[str, Any]


class FamilyView(BaseModel):
    id: uuid.UUID
    name: str
    manufacturer: str
    brand_name: str | None
    product_type: str | None
    category_code: str | None
    description: str | None
    properties_text: str | None
    source_document: str | None
    source_page: int | None
    variants: list[VariantView]


class VariantAttributesView(BaseModel):
    variant_id: uuid.UUID
    label: str
    # {key: {value, fact_id}} — the shape the node's reference preview takes (§8.2).
    attributes: dict[str, Any]
    identifiers: list[Any]
    additional_information: dict[str, Any]


class CatalogValue(BaseModel):
    value: dict[str, Any]
    source: str
    scope: str | None
    fact_id: str


class CatalogAttribute(BaseModel):
    key: str
    label: str
    type: str
    unit: str | None
    options: list[str]
    criticality: str


class OwnFact(BaseModel):
    """A value the supplier set itself (or its "not available"), which it may withdraw."""

    fact_id: uuid.UUID
    attribute_key: str
    variant_id: uuid.UUID | None
    value: dict[str, Any] | None
    unavailable: bool


class VariantValues(BaseModel):
    variant_id: uuid.UUID
    article_no: str
    label: str
    # A retired article is listed so it can be brought back; search and new assessments skip it.
    is_active: bool
    # The row as entered, so a new variant can start as a copy of this one.
    size_text: str | None
    order_unit: str | None
    units_per_order_unit: int | None
    order_units_per_shipping_unit: int | None
    values: dict[str, CatalogValue]
    unavailable: list[str]


class SupplierFamilyDetail(BaseModel):
    """Per attribute: the family's value, then each variant's effective value with its scope."""

    id: uuid.UUID
    name: str
    manufacturer: str
    brand_name: str | None
    product_type: str | None
    description: str | None
    properties_text: str | None
    category_code: str | None
    # The text changed since it was last read; `normalize_item` has yet to run.
    reading: bool
    attributes: list[CatalogAttribute]
    family_values: dict[str, CatalogValue]
    family_unavailable: list[str]
    variants: list[VariantValues]
    own_facts: list[OwnFact]


class CatalogEdit(BaseModel):
    """Exactly one of family and variant; a typed value, or unavailable=true."""

    family_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None
    attribute_key: str
    value: TypedValue | None = None
    unavailable: bool = False


class FamilyTextBody(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    manufacturer: str = Field(min_length=1, max_length=200)
    brand_name: str | None = Field(default=None, max_length=200)
    product_type: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    properties_text: str | None = Field(default=None, max_length=5000)


class FamilyCreate(FamilyTextBody):
    category_code: str


class FamilyEdit(BaseModel):
    """Either part may be left out: the text as a whole, or the category."""

    text: FamilyTextBody | None = None
    category_code: str | None = None


class VariantCreate(BaseModel):
    article_no: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=300)
    size_text: str | None = Field(default=None, max_length=300)
    order_unit: str | None = Field(default=None, max_length=60)
    units_per_order_unit: int | None = Field(default=None, gt=0)
    order_units_per_shipping_unit: int | None = Field(default=None, gt=0)
    gtin: str | None = Field(default=None, max_length=20)
    pzn: str | None = Field(default=None, max_length=20)
