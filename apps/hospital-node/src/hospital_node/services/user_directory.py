"""Node accounts and the directory the client uses to name hub subjects (N.1)."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.ids import new_subject_id
from hospital_node.models import User
from hospital_node.models.users import Role
from service_kit.errors import Conflict
from service_kit.security import PasswordHasher

MIN_PASSWORD_LENGTH = 12


def create_user(
    session: Session,
    hasher: PasswordHasher,
    *,
    email: str,
    password: str,
    role: Role,
    display_name: str,
) -> User:
    normalized = email.strip().lower()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"a password needs at least {MIN_PASSWORD_LENGTH} characters")
    if session.scalar(select(User.id).where(User.email == normalized)) is not None:
        raise Conflict("USER_EXISTS", f"a user with email {normalized} already exists")
    user = User(
        email=normalized,
        password_hash=hasher.hash(password),
        role=role,
        display_name=display_name,
        hub_subject_id=new_subject_id(),
    )
    session.add(user)
    session.flush()
    return user


def list_users(session: Session, *, include_inactive: bool) -> Sequence[User]:
    query = select(User).order_by(User.display_name)
    if not include_inactive:
        query = query.where(User.is_active.is_(True))
    return session.scalars(query).all()
