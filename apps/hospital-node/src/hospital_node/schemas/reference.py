from pydantic import BaseModel, Field

from equivalence_core.facts import HospitalSource
from equivalence_core.values import AttributeValue, TypedValue
from hospital_node.services.reference_link import Choice


class ReportedAttribute(BaseModel):
    value: TypedValue
    fact_id: str | None = Field(default=None, description="The hub fact the value came from.")


class ReferenceInput(BaseModel):
    """A hub variant's effective attributes, as `GET /catalog/variants/{id}/attributes` returned
    them to the client (unsigned, D37)."""

    variant_id: str = Field(min_length=1, max_length=200)
    label: str | None = Field(default=None, max_length=500)
    attributes: dict[str, ReportedAttribute]


class ReferenceSet(ReferenceInput):
    conflict_choices: dict[str, Choice] = {}


class FillView(BaseModel):
    key: str
    value: AttributeValue


class ConflictView(BaseModel):
    key: str
    ours: AttributeValue
    ours_source: HospitalSource
    theirs: AttributeValue


class PreviewView(BaseModel):
    fills: list[FillView]
    conflicts: list[ConflictView]
    kept_purchaser: list[str]
    identifiers_info: dict[str, TypedValue]
    ignored: list[str]
