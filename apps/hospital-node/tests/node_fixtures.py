"""Test helpers shared by the node tests (importable because pytest adds this directory
to `pythonpath`; conftest.py itself is not importable under --import-mode=importlib)."""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from hospital_node.core.security import PasswordHasher
from hospital_node.core.settings import NodeSettings
from hospital_node.llm.normalize_article import PURPOSE
from hospital_node.llm.outputs import NormalizeBatch, NormalizedArticle
from hospital_node.models import HospitalArticle, User
from hospital_node.models.users import Role
from hospital_node.services.seed import SeedReport, seed
from hospital_node.services.user_directory import create_user
from llm_client import FakeLLM, StructuredRequest

PASSWORD = "correct horse battery"
FIXTURES = Path(__file__).parent / "fixtures"


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class Users:
    """Creates accounts in the test database; every account uses PASSWORD."""

    def __init__(self, session: Session, hasher: PasswordHasher) -> None:
        self._session = session
        self._hasher = hasher

    def add(self, name: str, role: Role = Role.PURCHASER, *, active: bool = True) -> User:
        user = create_user(
            self._session,
            self._hasher,
            email=f"{name}@demo-ksp.example",
            password=PASSWORD,
            role=role,
            display_name=name.title(),
        )
        user.is_active = active
        self._session.commit()
        return user


def login(client: TestClient, user: User) -> dict[str, str]:
    """Authorization header for `user`."""
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def load_fixture(name: str) -> Any:
    return yaml.safe_load((FIXTURES / name).read_text())


def names_in(request: StructuredRequest[Any]) -> list[str]:
    """The article names inside a normalize_article request's data block."""
    block = re.search(r"<articles>(.*)</articles>", request.user, re.DOTALL)
    assert block is not None
    return [entry["name"] for entry in json.loads(block.group(1))]


def fake_normalizer() -> FakeLLM:
    """Answers normalize_article from fixtures/fake_llm_readings.yaml, whatever the batch."""
    readings = load_fixture("fake_llm_readings.yaml")

    def respond(request: StructuredRequest[Any]) -> NormalizeBatch:
        return NormalizeBatch(
            articles=[
                NormalizedArticle(index=index, **readings[name])
                for index, name in enumerate(names_in(request))
            ]
        )

    return FakeLLM({PURPOSE: respond})


def seed_demo(
    session: Session,
    hasher: PasswordHasher,
    settings: NodeSettings,
    clock: FakeClock,
    llm: FakeLLM | None = None,
    dataset: str = "demo_ksp",
) -> SeedReport:
    report = seed(
        session,
        dataset,
        password=PASSWORD,
        hasher=hasher,
        llm=llm,
        settings=settings,
        now=clock(),
    )
    session.commit()
    return report


def article(session: Session, internal_id: str) -> HospitalArticle:
    found = session.scalar(
        select(HospitalArticle).where(HospitalArticle.internal_id == internal_id)
    )
    assert found is not None, internal_id
    return found


def values(found: HospitalArticle) -> dict[str, Any]:
    """The projection's current values without their type wrappers."""
    assert found.projection is not None
    return {key: stored["value"] for key, stored in found.projection.attributes.items()}


def user(session: Session, role: Role) -> User:
    found = session.scalar(select(User).where(User.role == role).order_by(User.email))
    assert found is not None
    return found
