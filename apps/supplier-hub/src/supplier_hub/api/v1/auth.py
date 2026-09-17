from datetime import timedelta

from fastapi import APIRouter, status

from supplier_hub.api.deps import Context, DbSession, Token
from supplier_hub.models.identity import UserRole
from supplier_hub.schemas.auth import (
    ExchangeRequest,
    ExchangeResponse,
    LoginRequest,
    Me,
    TokenResponse,
)
from supplier_hub.services import auth, token_exchange

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, context: Context, session: DbSession) -> TokenResponse:
    issued = auth.login(
        session,
        context.hasher,
        body.email,
        body.password,
        now=context.clock(),
        ttl=timedelta(hours=context.settings.token_ttl_hours),
    )
    return TokenResponse(access_token=issued.access_token, expires_at=issued.expires_at)


@router.post("/token-exchange")
def token_exchange_endpoint(
    body: ExchangeRequest, context: Context, session: DbSession
) -> ExchangeResponse:
    """A node-signed assertion becomes a short-lived hub token (§17)."""
    settings = context.settings
    exchanged = token_exchange.exchange(
        session,
        body.assertion,
        audience=settings.hub_audience,
        now=context.clock(),
        ttl=timedelta(minutes=settings.exchange_ttl_minutes),
        leeway=settings.assertion_leeway_s,
    )
    return ExchangeResponse(
        access_token=exchanged.access_token,
        expires_at=exchanged.expires_at,
        tenant_alias=exchanged.tenant_alias,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(context: Context, session: DbSession, token: Token) -> None:
    auth.logout(session, token, now=context.clock())


@router.get("/me")
def me(context: Context, session: DbSession, token: Token) -> Me:
    row = auth.find_token(session, token, now=context.clock())
    if row.user is not None:
        return Me(
            kind="user",
            display_name=row.user.display_name,
            organization=row.user.org.name,
            role=UserRole(row.user.role),
        )
    assert row.principal is not None  # the token has exactly one owner (H.5)
    return Me(
        kind="purchaser",
        display_name=row.principal.subject_id,
        organization=row.principal.tenant.supplier_facing_alias or row.principal.tenant.name,
        subject_id=row.principal.subject_id,
    )
