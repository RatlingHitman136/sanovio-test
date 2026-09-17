from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import hospital_node.models  # noqa: F401  (registers every table)
from equivalence_core.exchange.keys import generate_private_key, write_private_key
from hospital_node.core.db import Base
from hospital_node.core.settings import NodeSettings
from hospital_node.main import create_app
from hospital_node.models import User
from hospital_node.models.users import Role
from hospital_node.services.seed import SeedReport
from node_fixtures import FakeClock, Users, seed_demo, user
from service_kit.db import make_engine, make_session_factory
from service_kit.security import PasswordHasher


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(tmp_path: Path) -> NodeSettings:
    key_file = tmp_path / "node.pem"
    write_private_key(generate_private_key(), key_file)
    return NodeSettings(
        _env_file=None,  # type: ignore[call-arg]
        node_signing_key_file=key_file,
        node_signing_kid="test-kid",
        database_url=f"sqlite:///{tmp_path / 'node.db'}",
        normalize_mode="rules",
    )


@pytest.fixture
def engine(settings: NodeSettings) -> Iterator[Engine]:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with make_session_factory(engine)() as session:
        yield session


@pytest.fixture(scope="session")
def hasher() -> PasswordHasher:
    return PasswordHasher()


@pytest.fixture
def users(session: Session, hasher: PasswordHasher) -> Users:
    return Users(session, hasher)


@pytest.fixture
def client(settings: NodeSettings, engine: Engine, clock: FakeClock) -> Iterator[TestClient]:
    with TestClient(create_app(settings, clock=clock)) as client:
        yield client


@pytest.fixture
def llm_settings(settings: NodeSettings) -> NodeSettings:
    return settings.model_copy(update={"normalize_mode": "llm"})


@pytest.fixture
def seeded(
    session: Session, hasher: PasswordHasher, settings: NodeSettings, clock: FakeClock
) -> SeedReport:
    """demo_ksp loaded in rules mode."""
    return seed_demo(session, hasher, settings, clock)


@pytest.fixture
def anna(session: Session, seeded: SeedReport) -> User:
    return user(session, Role.PURCHASER)


@pytest.fixture
def admin(session: Session, seeded: SeedReport) -> User:
    return user(session, Role.NODE_ADMIN)
