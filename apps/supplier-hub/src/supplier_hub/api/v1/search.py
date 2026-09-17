from fastapi import APIRouter

from supplier_hub.api.deps import CurrentPrincipal, DbSession
from supplier_hub.schemas.search import (
    CandidateView,
    PrecheckEntry,
    SearchRequest,
    SearchResponse,
    SearchSpecView,
)
from supplier_hub.services import candidate_search, requirement_intake
from supplier_hub.services.candidate_search import Candidate

router = APIRouter(tags=["search"])


@router.post("/search")
def search(body: SearchRequest, session: DbSession, _: CurrentPrincipal) -> SearchResponse:
    """Deterministic, read-only, nothing stored: the requirement is used and discarded (§15)."""
    accepted = requirement_intake.accept(session, body.requirement)
    result = candidate_search.search(
        session,
        accepted.payload,
        accepted.template,
        supplier_id=body.supplier_id,
        limit=body.limit,
    )
    return SearchResponse(
        search_spec=SearchSpecView(
            category=result.spec.category,
            hard_filters={
                key: value.model_dump(mode="json")
                for key, value in result.spec.hard_filters.items()
            },
            soft_criteria=list(result.spec.soft_criteria),
            hospital_gaps=list(result.spec.hospital_gaps),
        ),
        hospital_gaps=list(result.spec.hospital_gaps),
        excluded_by=result.excluded_by,
        candidates=[_candidate(candidate) for candidate in result.candidates],
    )


def _candidate(candidate: Candidate) -> CandidateView:
    variant = candidate.variant
    family = variant.family
    return CandidateView(
        variant_id=variant.id,
        article_no=variant.article_no,
        display_name=candidate.projection.display_name,
        supplier=family.supplier.name,
        family=family.name,
        manufacturer=family.manufacturer,
        score=candidate.score,
        coverage=candidate.coverage,
        critical_unknowns=candidate.critical_unknowns,
        identifier_match=candidate.identifier_match,
        precheck=[
            PrecheckEntry(
                attribute_key=judgment.attribute_key,
                status=judgment.status,
                criticality=judgment.criticality,
                supplier_value=(
                    judgment.supplier.value.model_dump(mode="json")
                    if judgment.supplier is not None
                    else None
                ),
            )
            for judgment in candidate.judgments
        ],
        additional_information=candidate.projection.additional_attributes,
    )
