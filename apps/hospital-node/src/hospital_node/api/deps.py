"""Request-scoped dependencies: the node context, a database session, the current user."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from hospital_node.core.clock import Clock
from hospital_node.core.secrets import NodeSecrets
from hospital_node.core.security import PasswordHasher
from hospital_node.core.settings import NodeSettings
from hospital_node.models import User
from hospital_node.models.users import Role
from hospital_node.services import auth
from hospital_node.services.errors import Forbidden, Unauthorized
from llm_client import LLMClient


@dataclass
class NodeContext:
    """Everything a request may need, built once by the app factory."""

    settings: NodeSettings
    session_factory: sessionmaker[Session]
    clock: Clock
    llm: LLMClient | None = None
    hasher: PasswordHasher = field(default_factory=PasswordHasher)
    # Loaded in the lifespan, so a bad key stops startup rather than the first request.
    secrets: NodeSecrets | None = None

    @property
    def signing(self) -> NodeSecrets:
        if self.secrets is None:
            raise RuntimeError("secrets are loaded at startup")
        return self.secrets


def get_context(request: Request) -> NodeContext:
    context: NodeContext = request.app.state.node
    return context


Context = Annotated[NodeContext, Depends(get_context)]


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
    return auth.authenticate(session, token, now=context.clock())


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(*roles: Role) -> Callable[[User], User]:
    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise Forbidden("this action needs the role " + " or ".join(roles))
        return user

    return check


Purchaser = Annotated[User, Depends(require_role(Role.PURCHASER))]
NodeAdmin = Annotated[User, Depends(require_role(Role.NODE_ADMIN))]
AnyNodeUser = Annotated[User, Depends(require_role(Role.PURCHASER, Role.NODE_ADMIN))]
