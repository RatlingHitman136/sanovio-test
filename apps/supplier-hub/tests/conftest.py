from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import supplier_hub.models  # noqa: F401  (registers every table)
from hub_fixtures import FakeClock, Orgs, login, purchaser_headers, seed_hub_demo
from service_kit.db import make_engine, make_session_factory
from service_kit.security import PasswordHasher
from supplier_hub.core.db import Base
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fakes import fake_normalizer
from supplier_hub.main import create_app
from supplier_hub.models import User
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
        # Tests drive the queue themselves (`HubContext.run_jobs`), never a thread.
        worker_enabled=False,
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


@pytest.fixture
def buyer(client: TestClient, orgs: Orgs, clock: FakeClock, seeded: SeedReport) -> dict[str, str]:
    """A ten_ksp purchaser, signed in through a node assertion."""
    return purchaser_headers(client, orgs, clock)


@pytest.fixture
def bd(client: TestClient, session: Session, seeded: SeedReport) -> dict[str, str]:
    """BD's seeded catalog user."""
    user = session.scalar(select(User).where(User.email == "catalog@bd-demo.example"))
    assert user is not None
    return login(client, user)


@pytest.fixture
def operator(client: TestClient, session: Session, seeded: SeedReport) -> dict[str, str]:
    """The seeded operator (ops@sanovio-demo.example)."""
    user = session.scalar(select(User).where(User.email == "ops@sanovio-demo.example"))
    assert user is not None
    return login(client, user)
