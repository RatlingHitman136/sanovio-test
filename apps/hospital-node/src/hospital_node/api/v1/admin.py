from fastapi import APIRouter

from equivalence_core.exchange.keys import jwk_thumbprint, public_jwk
from hospital_node.api.deps import Context, NodeAdmin
from hospital_node.schemas.admin import SigningKeyView

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/signing-key")
def signing_key(context: Context, _: NodeAdmin) -> SigningKeyView:
    """The public half only, for registration at the hub (§17 onboarding)."""
    secrets = context.signing
    jwk = public_jwk(secrets.signing_key, secrets.signing_kid)
    return SigningKeyView(kid=secrets.signing_kid, public_jwk=jwk, fingerprint=jwk_thumbprint(jwk))
