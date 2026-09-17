import uuid
from typing import Any

from pydantic import BaseModel, Field

from equivalence_core.comparators import ComparisonStatus
from equivalence_core.exchange.requirement import RequirementPayload
from supplier_hub.services.candidate_search import DEFAULT_LIMIT, MAX_LIMIT


class SearchRequest(BaseModel):
    """Only the requirement plus two options: no paging, no relaxation (D54)."""

    requirement: RequirementPayload
    supplier_id: uuid.UUID | None = None
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class SearchSpecView(BaseModel):
    category: str
    hard_filters: dict[str, Any]
    soft_criteria: list[str]
    # Attributes the hospital does not know; marking a current product fills them (§15.3).
    hospital_gaps: list[str]


class PrecheckEntry(BaseModel):
    attribute_key: str
    status: ComparisonStatus
    criticality: str
    supplier_value: Any | None


class CandidateView(BaseModel):
    variant_id: uuid.UUID
    article_no: str
    display_name: str
    supplier: str
    family: str
    manufacturer: str
    score: float
    coverage: float
    critical_unknowns: int
    identifier_match: str | None
    precheck: list[PrecheckEntry]
    additional_information: dict[str, Any]


class SearchResponse(BaseModel):
    search_spec: SearchSpecView
    hospital_gaps: list[str]
    excluded_by: dict[str, int]
    candidates: list[CandidateView]
