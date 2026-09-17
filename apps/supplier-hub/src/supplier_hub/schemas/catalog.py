import uuid
from typing import Any

from pydantic import BaseModel


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
