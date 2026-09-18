"""Development-only endpoints; mounted only when APP_ENV=dev."""

import uuid

from fastapi import APIRouter

from service_kit.errors import Conflict, NotFound
from supplier_hub.api.deps import Context, DbSession, Operator
from supplier_hub.models import Assessment
from supplier_hub.services import supplier_simulator

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/assessments/{assessment_id}/simulate-supplier")
def simulate_supplier(
    assessment_id: uuid.UUID, context: Context, session: DbSession, _: Operator
) -> dict[str, str]:
    """Answers the open supplier questions from a synthetic datasheet (§21)."""
    assessment = session.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFound("assessment not found")
    if context.llm is None:
        raise Conflict("LLM_UNAVAILABLE", "the simulator needs an LLM client")
    supplier_simulator.simulate(
        session, assessment, llm=context.llm, settings=context.settings, now=context.clock()
    )
    return {"status": assessment.status}
