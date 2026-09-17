"""Test helpers shared by the hub tests (importable because pytest adds this directory to
`pythonpath`; conftest.py itself is not importable under --import-mode=importlib)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from equivalence_core.exchange.assertion import ASSERTION_TYP
from equivalence_core.exchange.jws import sign
from equivalence_core.exchange.keys import generate_private_key, public_jwk
from llm_client import FakeLLM
from service_kit.security import PasswordHasher
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fake_readings import scripted_readings
from supplier_hub.models import Organization, User
from supplier_hub.models.identity import UserRole
from supplier_hub.models.organizations import OrganizationType
from supplier_hub.services.seed import SeedReport, seed

PASSWORD = "correct horse battery"


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class Orgs:
    """Creates organizations and their users; every account uses PASSWORD."""

    def __init__(self, session: Session, hasher: PasswordHasher) -> None:
        self._session = session
        self._hasher = hasher

    def hospital(
        self,
        code: str = "ten_ksp",
        name: str = "Demo Kantonsspital",
        alias: str = "Hospital H-7F3A",
    ) -> Organization:
        return self._add(code, name, OrganizationType.HOSPITAL, alias=alias)

    def supplier(self, code: str = "org_bd", name: str = "BD") -> Organization:
        return self._add(code, name, OrganizationType.SUPPLIER)

    def operator(self, code: str = "org_ops", name: str = "Sanovio Operations") -> Organization:
        return self._add(code, name, OrganizationType.OPERATOR)

    def user(self, org: Organization, email: str, role: UserRole) -> User:
        user = User(
            org_id=org.id,
            email=email,
            password_hash=self._hasher.hash(PASSWORD),
            role=role,
            display_name=email.split("@")[0].title(),
        )
        self._session.add(user)
        self._session.commit()
        return user

    def _add(
        self, code: str, name: str, kind: OrganizationType, alias: str | None = None
    ) -> Organization:
        org = Organization(code=code, name=name, type=kind, supplier_facing_alias=alias)
        self._session.add(org)
        self._session.commit()
        return org


def login(client: TestClient, user: User) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@dataclass(frozen=True)
class NodeKey:
    """A hospital node's key pair as the hub would know it: private here, public registered."""

    private: Ed25519PrivateKey
    kid: str
    tenant_code: str

    def jwk(self) -> dict[str, str]:
        return public_jwk(self.private, self.kid)

    def assertion(
        self,
        now: datetime,
        *,
        subject: str = "sub_7QF2M4XK9P3TZC8W1N6R",
        audience: str = "sanovio-hub",
        lifetime_s: int = 300,
        typ: str = ASSERTION_TYP,
        issuer: str | None = None,
        jti: str | None = None,
        scope: str = "purchaser",
    ) -> str:
        issued_at = int(now.timestamp())
        claims = {
            "iss": issuer or self.tenant_code,
            "sub": subject,
            "aud": audience,
            "scope": scope,
            "iat": issued_at,
            "exp": issued_at + lifetime_s,
            "jti": jti or str(uuid.uuid4()),
        }
        return sign(claims, self.private, kid=self.kid, typ=typ)


def register_node_key(
    client: TestClient,
    operator_headers: dict[str, str],
    tenant_id: str,
    key: NodeKey,
) -> dict[str, str]:
    response = client.post(
        f"/api/v1/admin/tenants/{tenant_id}/signing-keys",
        json={"public_jwk": key.jwk()},
        headers=operator_headers,
    )
    assert response.status_code == 200, response.text
    body: dict[str, str] = response.json()
    return body


def node_key(tenant_code: str = "ten_ksp", kid: str = "ksp-2026-09") -> NodeKey:
    return NodeKey(private=generate_private_key(), kid=kid, tenant_code=tenant_code)


def seed_hub_demo(
    session: Session,
    hasher: PasswordHasher,
    settings: HubSettings,
    clock: FakeClock,
    llm: FakeLLM | None = None,
) -> SeedReport:
    report = seed(
        session,
        password=PASSWORD,
        hasher=hasher,
        llm=llm,
        settings=settings,
        now=clock(),
    )
    session.commit()
    return report


FAMILY_READINGS = scripted_readings()
