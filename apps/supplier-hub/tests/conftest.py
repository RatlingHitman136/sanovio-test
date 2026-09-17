from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import supplier_hub.models  # noqa: F401  (registers every table)
from hub_fixtures import FakeClock, Orgs, seed_hub_demo
from service_kit.db import make_engine, make_session_factory
from service_kit.security import PasswordHasher
from supplier_hub.core.db import Base
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fake_readings import fake_normalizer
from supplier_hub.main import create_app
from supplier_hub.services.seed import SeedReport


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(tmp_path: Path) -> HubSettings:
    return HubSettings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=f"sqlite:///{tmp_path / 'hub.db'}",
        llm_mode="fake",
    )


@pytest.fixture
def engine(settings: HubSettings) -> Iterator[Engine]:
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
def orgs(session: Session, hasher: PasswordHasher) -> Orgs:
    return Orgs(session, hasher)


@pytest.fixture
def client(settings: HubSettings, engine: Engine, clock: FakeClock) -> Iterator[TestClient]:
    with TestClient(create_app(settings, clock=clock)) as client:
        yield client


@pytest.fixture
def seeded(
    session: Session, hasher: PasswordHasher, settings: HubSettings, clock: FakeClock
) -> SeedReport:
    """Both catalogs loaded with the scripted normalize_item answers."""
    return seed_hub_demo(session, hasher, settings, clock, fake_normalizer())
