from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from hospital_node.models import ApiToken
from hospital_node.models.users import Role
from hospital_node.services import auth
from hospital_node.services.user_directory import create_user, list_users
from node_fixtures import PASSWORD, FakeClock, Users
from service_kit.errors import Conflict, Unauthorized
from service_kit.security import PasswordHasher

TTL = timedelta(hours=8)


def test_login_issues_a_token_that_authenticates(
    session: Session, hasher: PasswordHasher, users: Users, clock: FakeClock
) -> None:
    anna = users.add("anna")

    issued = auth.login(session, hasher, " Anna@Demo-KSP.example ", PASSWORD, now=clock(), ttl=TTL)
    clock.advance(minutes=5)
    user = auth.authenticate(session, issued.access_token, now=clock())

    assert user.id == anna.id
    assert issued.expires_at == clock() - timedelta(minutes=5) + TTL


def test_last_use_is_recorded(
    session: Session, hasher: PasswordHasher, users: Users, clock: FakeClock
) -> None:
    anna = users.add("anna")
    issued = auth.login(session, hasher, anna.email, PASSWORD, now=clock(), ttl=TTL)
    clock.advance(minutes=3)

    auth.authenticate(session, issued.access_token, now=clock())

    (token,) = session.scalars(select(ApiToken)).all()
    assert token.last_used_at == clock()


@pytest.mark.parametrize(
    ("email", "password"),
    [("anna@demo-ksp.example", "wrong password"), ("nobody@demo-ksp.example", PASSWORD)],
)
def test_bad_credentials_get_the_same_answer(
    session: Session,
    hasher: PasswordHasher,
    users: Users,
    clock: FakeClock,
    email: str,
    password: str,
) -> None:
    users.add("anna")

    with pytest.raises(Unauthorized, match="invalid email or password"):
        auth.login(session, hasher, email, password, now=clock(), ttl=TTL)


def test_inactive_users_cannot_log_in(
    session: Session, hasher: PasswordHasher, users: Users, clock: FakeClock
) -> None:
    users.add("anna", active=False)

    with pytest.raises(Unauthorized):
        auth.login(session, hasher, "anna@demo-ksp.example", PASSWORD, now=clock(), ttl=TTL)


def test_expired_and_revoked_tokens_are_rejected(
    session: Session, hasher: PasswordHasher, users: Users, clock: FakeClock
) -> None:
    anna = users.add("anna")
    expiring = auth.login(session, hasher, anna.email, PASSWORD, now=clock(), ttl=TTL)
    revoked = auth.login(session, hasher, anna.email, PASSWORD, now=clock(), ttl=TTL)

    auth.logout(session, revoked.access_token, now=clock())
    with pytest.raises(Unauthorized):
        auth.authenticate(session, revoked.access_token, now=clock())

    clock.advance(hours=8)
    with pytest.raises(Unauthorized):
        auth.authenticate(session, expiring.access_token, now=clock())


def test_a_deactivated_user_loses_existing_sessions(
    session: Session, hasher: PasswordHasher, users: Users, clock: FakeClock
) -> None:
    anna = users.add("anna")
    issued = auth.login(session, hasher, anna.email, PASSWORD, now=clock(), ttl=TTL)

    anna.is_active = False

    with pytest.raises(Unauthorized):
        auth.authenticate(session, issued.access_token, now=clock())


def test_users_get_a_hub_subject_and_unique_email(
    session: Session, hasher: PasswordHasher, users: Users
) -> None:
    anna = users.add("anna")

    assert anna.hub_subject_id.startswith("sub_")
    with pytest.raises(Conflict):
        create_user(
            session,
            hasher,
            email="ANNA@demo-ksp.example",
            password=PASSWORD,
            role=Role.PURCHASER,
            display_name="Other Anna",
        )


def test_short_passwords_are_refused(session: Session, hasher: PasswordHasher) -> None:
    with pytest.raises(ValueError, match="12 characters"):
        create_user(
            session,
            hasher,
            email="x@y.example",
            password="short",
            role=Role.PURCHASER,
            display_name="X",
        )


def test_directory_hides_inactive_users_unless_asked(session: Session, users: Users) -> None:
    users.add("anna")
    users.add("bert", active=False)

    assert [u.display_name for u in list_users(session, include_inactive=False)] == ["Anna"]
    assert len(list_users(session, include_inactive=True)) == 2
