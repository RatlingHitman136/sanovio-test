"""Loads the demo hub (ARCHITECTURE §21): organizations, the registry, catalogs, projections."""

import json
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from llm_client import LLMClient
from service_kit.security import PasswordHasher
from supplier_hub.core.db import Base
from supplier_hub.core.settings import HubSettings
from supplier_hub.models import Assessment, Organization, User
from supplier_hub.models.identity import UserRole
from supplier_hub.models.organizations import OrganizationType
from supplier_hub.services import catalog, normalization, templates

CATALOGS = ("bbraun", "bd")
OPERATOR = {
    "code": "org_ops",
    "name": "Sanovio Operations",
    "email": "ops@sanovio-demo.example",
    "display_name": "Hub Operator",
}
TENANTS = (
    {"code": "ten_ksp", "name": "Demo Kantonsspital", "alias": "Hospital H-7F3A"},
    {"code": "ten_spital2", "name": "Demo Spital Zwei", "alias": "Hospital H-2C91"},
)


class SeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class SeedReport:
    tenants: int
    suppliers: int
    families: int
    variants: int


def seed(
    session: Session,
    *,
    password: str,
    hasher: PasswordHasher,
    llm: LLMClient | None,
    settings: HubSettings,
    now: datetime,
    reset: bool = False,
) -> SeedReport:
    if session.scalar(select(Organization.id).limit(1)) is not None:
        if not reset:
            raise SeedError("the database already has data; pass reset to replace it")
        _wipe(session)

    operator_org = _organization(
        session, OPERATOR["code"], OPERATOR["name"], OrganizationType.OPERATOR
    )
    _user(
        session,
        hasher,
        operator_org,
        OPERATOR["email"],
        OPERATOR["display_name"],
        UserRole.OPERATOR,
        password,
    )
    for tenant in TENANTS:
        _organization(
            session,
            tenant["code"],
            tenant["name"],
            OrganizationType.HOSPITAL,
            alias=tenant["alias"],
            country="CH",
        )

    templates.seed_templates(session, now=now)
    known = templates.definitions(session)

    families = []
    for name in CATALOGS:
        data = _load(name)
        supplier_data = data["supplier"]
        supplier = _organization(
            session,
            supplier_data["code"],
            supplier_data["name"],
            OrganizationType.SUPPLIER,
            country=supplier_data.get("country"),
        )
        account = supplier_data["user"]
        _user(
            session,
            hasher,
            supplier,
            account["email"],
            account["display_name"],
            UserRole.SUPPLIER,
            password,
        )
        for family_data in data["families"]:
            template = known[family_data["category_code"]]
            families.append(
                catalog.ingest_family(session, supplier, family_data, template, now=now)
            )

    normalization.normalize(session, families, llm=llm, settings=settings, now=now)
    return SeedReport(
        tenants=len(TENANTS),
        suppliers=len(CATALOGS),
        families=len(families),
        variants=sum(len(family.variants) for family in families),
    )


def _organization(
    session: Session,
    code: str,
    name: str,
    kind: OrganizationType,
    *,
    alias: str | None = None,
    country: str | None = None,
) -> Organization:
    org = Organization(
        code=code, name=name, type=kind, supplier_facing_alias=alias, country=country
    )
    session.add(org)
    session.flush()
    return org


def _user(
    session: Session,
    hasher: PasswordHasher,
    org: Organization,
    email: str,
    display_name: str,
    role: UserRole,
    password: str,
) -> User:
    user = User(
        org_id=org.id,
        email=email.lower(),
        password_hash=hasher.hash(password),
        role=role,
        display_name=display_name,
    )
    session.add(user)
    session.flush()
    return user


def _load(name: str) -> Any:
    path = resources.files("supplier_hub") / "seed" / "catalog" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _wipe(session: Session) -> None:
    # Assessments and requirements point at each other; no delete order satisfies both.
    session.execute(update(Assessment).values(current_requirement_id=None))
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(delete(table))
    session.flush()
