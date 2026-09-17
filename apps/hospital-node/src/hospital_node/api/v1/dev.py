"""Development-only endpoints; mounted only when APP_ENV=dev."""

from fastapi import APIRouter

from hospital_node.api.deps import Context, DbSession, NodeAdmin
from hospital_node.schemas.admin import ResetSeed, SeedResult
from hospital_node.services.errors import Conflict
from hospital_node.services.normalization import NormalizationUnavailable
from hospital_node.services.seed import SeedError, seed

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/reset-seed")
def reset_seed(body: ResetSeed, context: Context, session: DbSession, _: NodeAdmin) -> SeedResult:
    """Replaces all node data with a demo dataset; every session, yours included, ends."""
    password = context.settings.node_seed_password
    if password is None or not password.get_secret_value():
        raise Conflict("SEED_PASSWORD_MISSING", "NODE_SEED_PASSWORD is not set on the node")
    try:
        report = seed(
            session,
            body.dataset,
            password=password.get_secret_value(),
            hasher=context.hasher,
            llm=context.llm,
            settings=context.settings,
            now=context.clock(),
            reset=True,
        )
    except (SeedError, NormalizationUnavailable) as exc:
        raise Conflict("SEED_FAILED", str(exc)) from exc
    return SeedResult(dataset=body.dataset, users=report.users, articles=report.articles)
