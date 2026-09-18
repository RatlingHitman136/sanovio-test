"""Request-scoped dependencies: the hub context, a database session, the caller."""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from llm_client import LLMClient
from service_kit.clock import Clock
from service_kit.errors import Forbidden, Unauthorized
from service_kit.security import PasswordHasher
from supplier_hub.core.settings import HubSettings
from supplier_hub.jobs.worker import Handler, run_pending
from supplier_hub.models import HospitalPrincipal, Organization, User
from supplier_hub.models.identity import UserRole
from supplier_hub.models.jobs import JobKind
from supplier_hub.services import assessment, auth


@dataclass
class HubContext:
    settings: HubSettings
    session_factory: sessionmaker[Session]
    clock: Clock
    llm: LLMClient | None = None
    hasher: PasswordHasher = field(default_factory=PasswordHasher)
    handlers: Mapping[JobKind, Handler] = field(default_factory=dict)

    def run_jobs(self) -> int:
        """Runs every ready job now: how tests and inline setups drive the loop (§12)."""
        return run_pending(
            self.session_factory, self.handlers, clock=self.clock, on_give_up=assessment.give_up
        )


def get_context(request: Request) -> HubContext:
    context: HubContext = request.app.state.hub
    return context


Context = Annotated[HubContext, Depends(get_context)]


def get_session(context: Context) -> Iterator[Session]:
    # Commits before the response is sent (function scope), so a 2xx means the data is stored.
    with context.session_factory() as session:
        yield session
        session.commit()


DbSession = Annotated[Session, Depends(get_session, scope="function")]

_bearer = HTTPBearer(auto_error=False)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def bearer_token(credentials: Credentials) -> str:
    if credentials is None:
        raise Unauthorized("missing bearer token")
    return credentials.credentials


Token = Annotated[str, Depends(bearer_token)]


def current_user(context: Context, session: DbSession, token: Token) -> User:
    """A supplier user or an operator; hospital staff never have an account here."""
    return auth.authenticate_user(session, token, now=context.clock())


CurrentUser = Annotated[User, Depends(current_user)]


@dataclass(frozen=True)
class Principal:
    """A purchaser, known only through the token they exchanged (§17)."""

    tenant: Organization
    principal: HospitalPrincipal


def current_principal(context: Context, session: DbSession, token: Token) -> Principal:
    row = auth.find_token(session, token, now=context.clock())
    if row.principal is None or row.tenant_id is None:
        raise Forbidden("this endpoint is for hospital purchasers")
    if row.principal.is_blocked or not row.principal.tenant.is_active:
        raise Unauthorized("invalid or expired token")
    return Principal(tenant=row.principal.tenant, principal=row.principal)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require_role(*roles: UserRole) -> Callable[[User], User]:
    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise Forbidden("this action needs the role " + " or ".join(roles))
        return user

    return check


Operator = Annotated[User, Depends(require_role(UserRole.OPERATOR))]
Supplier = Annotated[User, Depends(require_role(UserRole.SUPPLIER))]
AnyHubUser = Annotated[User, Depends(require_role(UserRole.OPERATOR, UserRole.SUPPLIER))]
