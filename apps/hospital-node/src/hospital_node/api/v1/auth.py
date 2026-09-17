from datetime import timedelta

from fastapi import APIRouter, status

from hospital_node.api.deps import Context, CurrentUser, DbSession, Token
from hospital_node.models.users import Role
from hospital_node.schemas.auth import LoginRequest, Me, TokenResponse
from hospital_node.services import auth

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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(context: Context, session: DbSession, token: Token, _: CurrentUser) -> None:
    auth.logout(session, token, now=context.clock())


@router.get("/me")
def me(user: CurrentUser) -> Me:
    return Me(
        email=user.email,
        display_name=user.display_name,
        role=Role(user.role),
        hub_subject_id=user.hub_subject_id,
    )
