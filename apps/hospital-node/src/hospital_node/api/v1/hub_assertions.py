from datetime import UTC, datetime

from fastapi import APIRouter

from hospital_node.api.deps import Context, DbSession, Purchaser
from hospital_node.models.exchange import EgressKind
from hospital_node.schemas.exchange import AssertionResponse
from hospital_node.services import assertion_signer, egress_log

router = APIRouter(prefix="/hub-assertions", tags=["exchange"])


@router.post("")
def create_assertion(context: Context, session: DbSession, user: Purchaser) -> AssertionResponse:
    """Signs a five-minute assertion for the hub's token exchange (§17)."""
    token, claims = assertion_signer.sign_assertion(
        context.signing, context.settings, user, context.clock()
    )
    egress_log.issue(
        session,
        kind=EgressKind.ASSERTION,
        user=user,
        content=claims,  # the claims only, never the token
        limits=egress_log.limits_for(EgressKind.ASSERTION, context.settings),
        now=context.clock(),
        jti=claims["jti"],
        kid=context.signing.signing_kid,
    )
    return AssertionResponse(
        assertion=token, expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC)
    )
