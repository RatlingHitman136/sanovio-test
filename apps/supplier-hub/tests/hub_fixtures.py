"""Test helpers shared by the hub tests (importable because pytest adds this directory to
`pythonpath`; conftest.py itself is not importable under --import-mode=importlib)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.exchange.assertion import ASSERTION_TYP
from equivalence_core.exchange.jws import sign
from equivalence_core.exchange.keys import generate_private_key, public_jwk
from equivalence_core.templates import load_seed_templates
from llm_client import FakeLLM
from service_kit.security import PasswordHasher
from supplier_hub.api.deps import HubContext
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fakes import scripted_readings
from supplier_hub.models import (
    Assessment,
    HospitalPrincipal,
    Organization,
    ProductVariant,
    User,
)
from supplier_hub.models.assessments import AssessmentStatus
from supplier_hub.models.identity import UserRole
from supplier_hub.models.organizations import OrganizationType
from supplier_hub.services.seed import SeedReport, seed

PASSWORD = "correct horse battery"
SUBJECT = "sub_7QF2M4XK9P3TZC8W1N6R"


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
        subject: str = SUBJECT,
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


def principal(
    session: Session, tenant_code: str = "ten_ksp", subject: str = SUBJECT
) -> HospitalPrincipal:
    """A purchaser the hub already knows, as the token exchange would have left them."""
    tenant = session.scalar(select(Organization).where(Organization.code == tenant_code))
    assert tenant is not None, tenant_code
    found = session.scalar(
        select(HospitalPrincipal).where(
            HospitalPrincipal.tenant_id == tenant.id, HospitalPrincipal.subject_id == subject
        )
    )
    if found is None:
        now = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
        found = HospitalPrincipal(
            tenant_id=tenant.id, subject_id=subject, first_seen_at=now, last_seen_at=now
        )
        session.add(found)
        session.flush()
    return found


def variant(session: Session, article_no: str) -> ProductVariant:
    found = session.scalar(select(ProductVariant).where(ProductVariant.article_no == article_no))
    assert found is not None, article_no
    return found


def bare_assessment(
    session: Session,
    status: AssessmentStatus = AssessmentStatus.ASSESSING,
    article_no: str = "300912",
) -> Assessment:
    """An assessment row without a round, for tests of the rules of motion only."""
    buyer = principal(session)
    target = variant(session, article_no)
    row = Assessment(
        hospital_tenant_id=buyer.tenant_id,
        supplier_id=target.supplier_id,
        article_ref="ar_5MZQ4K7T2V9C",
        variant_id=target.id,
        template_code="syringe_single_use",
        status=status,
        max_rounds=3,
        created_by_principal_id=buyer.id,
        created_at=datetime(2026, 9, 17, 9, 0, tzinfo=UTC),
    )
    session.add(row)
    session.flush()
    return row


def purchaser_headers(
    client: TestClient, orgs: Orgs, clock: FakeClock, tenant_code: str = "ten_ksp"
) -> dict[str, str]:
    """A purchaser arriving the only way they can: a node assertion exchanged (§17)."""
    operator_email = f"ops-{tenant_code}@sanovio.example"
    operator = login(
        client,
        orgs.user(orgs.operator(f"ops_{tenant_code}", "Ops"), operator_email, UserRole.OPERATOR),
    )
    tenant = next(
        t
        for t in client.get("/api/v1/admin/tenants", headers=operator).json()
        if t["code"] == tenant_code
    )
    key = node_key(tenant_code=tenant_code, kid=f"{tenant_code}-test")
    register_node_key(client, operator, tenant["id"], key)
    exchanged = client.post(
        "/api/v1/auth/token-exchange", json={"assertion": key.assertion(clock())}
    )
    assert exchanged.status_code == 200, exchanged.text
    return {"Authorization": f"Bearer {exchanged.json()['access_token']}"}


# CSV #3 as the node sends it after marking Injekt as the current product (§21, scenario 1).
ART_03_LINKED: dict[str, Any] = {
    "mdr_class": {"type": "enum", "value": "IIA"},
    "sterile": {"type": "bool", "value": True},
    "single_use": {"type": "bool", "value": True},
    "latex_free": {"type": "bool", "value": True},
    "dehp_free": {"type": "bool", "value": True},
    "standards": {"type": "list", "value": ["ISO 7886-1"]},
    "nominal_volume_ml": {"type": "number", "value": 10, "unit": "ml"},
    "usable_volume_ml": {"type": "number", "value": 12, "unit": "ml"},
    "connector": {"type": "enum", "value": "LUER_LOCK"},
    "cone_position": {"type": "enum", "value": "CENTRIC"},
    "design": {"type": "enum", "value": "TWO_PART"},
    "graduation_step_ml": {"type": "number", "value": 0.5, "unit": "ml"},
    "needle_included": {"type": "bool", "value": False},
    "safety_mechanism": {"type": "bool", "value": False},
    "pump_compatible": {"type": "bool", "value": False},
    "light_protected": {"type": "bool", "value": False},
    "iso_7886_1_compliant": {"type": "bool", "value": True},
}

# The same, with the scale already known at the node: round 1 asks only the supplier.
ART_03_WITH_SCALE = ART_03_LINKED | {"special_scale": {"type": "text", "value": "keine"}}


def requirement(
    attributes: dict[str, Any],
    *,
    template_code: str = "syringe_single_use",
    article_ref: str = "ar_5MZQ4K7T2V9C",
    **extra: Any,
) -> dict[str, Any]:
    """A requirement as JSON, exactly as the client forwards it from the node."""
    keys = load_seed_templates()[template_code].keys
    unavailable = set(extra.get("unavailable_attributes", ()))
    return {
        "requirement_version": 1,
        "article_ref": article_ref,
        "template_code": template_code,
        "attributes": attributes,
        "attribute_origin": {key: "REFERENCE" for key in attributes},
        "unknown_attributes": [k for k in keys if k not in attributes and k not in unavailable],
        **extra,
    }


def run_jobs(client: TestClient) -> None:
    """The queue drained inline: tests never start the worker thread."""
    context: HubContext = client.app.state.hub  # type: ignore[attr-defined]
    context.run_jobs()


def fetch(client: TestClient, headers: dict[str, str], assessment_id: str) -> Any:
    response = client.get(f"/api/v1/assessments/{assessment_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def open_assessment(
    client: TestClient,
    headers: dict[str, str],
    session: Session,
    article_no: str,
    attributes: dict[str, Any] = ART_03_LINKED,
    **req: Any,
) -> Any:
    """The 202 body; the round itself runs with the next `run_jobs`."""
    body = {
        "requirement": requirement(attributes, **req),
        "variant_id": str(variant(session, article_no).id),
    }
    response = client.post("/api/v1/assessments", json=body, headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


def ask_free_question(
    client: TestClient, buyer: dict[str, str], assessment_id: str, text: str, **body: Any
) -> Any:
    """A purchaser's question without an attribute: it starts an attribute proposal (§7.2)."""
    return client.post(
        f"/api/v1/assessments/{assessment_id}/questions",
        json={
            "version": fetch(client, buyer, assessment_id)["version"],
            "addressee": "SUPPLIER",
            "attribute_key": None,
            "text": text,
        }
        | body,
        headers=buyer,
    )


def send_questions(client: TestClient, headers: dict[str, str], assessment_id: str) -> Any:
    version = fetch(client, headers, assessment_id)["version"]
    response = client.post(
        f"/api/v1/assessments/{assessment_id}/send-questions",
        json={"version": version},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def supplier_answers(
    client: TestClient,
    supplier: dict[str, str],
    assessment_id: str,
    typed: dict[str, Any],
    comments: dict[str, str] | None = None,
    cannot_provide: tuple[str, ...] = (),
) -> Any:
    """Answers every sent question, family-wide unless the supplier cannot provide it."""
    request = client.get(f"/api/v1/supplier/requests/{assessment_id}", headers=supplier)
    assert request.status_code == 200, request.text
    answers = []
    for question in request.json()["questions"]:
        key = question["attribute_key"]
        entry: dict[str, Any] = {"question_id": question["id"], "applies_to_family": True}
        if key in cannot_provide:
            entry |= {
                "cannot_provide": True,
                "comment": "Nicht spezifiziert.",
                "applies_to_family": False,
            }
        elif comments and key in comments:
            entry["comment"] = comments[key]
        else:
            entry["value"] = typed[key]
        answers.append(entry)
    saved = client.put(
        f"/api/v1/supplier/requests/{assessment_id}/answers",
        json={"answers": answers},
        headers=supplier,
    )
    assert saved.status_code == 200, saved.text
    submitted = client.post(f"/api/v1/supplier/requests/{assessment_id}/submit", headers=supplier)
    assert submitted.status_code == 200, submitted.text
    return request.json()
