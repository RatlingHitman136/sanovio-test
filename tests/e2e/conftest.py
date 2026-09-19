"""Both services in one process, driven only through the demo client (ARCHITECTURE §6).

Node `ten_ksp` and the hub run as FastAPI apps on their own SQLite files; `ten_spital2` exists
only at the hub (D55). No network, no threads: the hub's worker is off and the client's wait
drains the job queue instead, so every run is deterministic.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import hospital_node.models  # noqa: F401  (registers every node table)
import supplier_hub.models  # noqa: F401  (registers every hub table)
from e2e_system import System, register_node_key
from equivalence_core.exchange.keys import generate_private_key, write_private_key
from hospital_node.core.db import Base as NodeBase
from hospital_node.core.settings import NodeSettings
from hospital_node.main import create_app as create_node
from hub_fixtures import FakeClock, seed_hub_demo
from node_fixtures import fake_normalizer as node_normalizer
from node_fixtures import seed_demo
from service_kit.db import make_engine, make_session_factory
from service_kit.security import PasswordHasher
from supplier_hub.core.db import Base as HubBase
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fakes import fake_llm
from supplier_hub.main import create_app as create_hub


@pytest.fixture(scope="session")
def hasher() -> PasswordHasher:
    return PasswordHasher()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def node_settings(tmp_path: Path) -> NodeSettings:
    key_file = tmp_path / "node_ksp.pem"
    write_private_key(generate_private_key(), key_file)
    return NodeSettings(
        _env_file=None,  # type: ignore[call-arg]
        node_signing_key_file=key_file,
        node_signing_kid="ksp-e2e",
        database_url=f"sqlite:///{tmp_path / 'node.db'}",
        normalize_mode="llm",
    )


@pytest.fixture
def hub_settings(tmp_path: Path) -> HubSettings:
    return HubSettings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=f"sqlite:///{tmp_path / 'hub.db'}",
        llm_mode="fake",
        worker_enabled=False,
    )


@pytest.fixture
def system(
    node_settings: NodeSettings,
    hub_settings: HubSettings,
    clock: FakeClock,
    hasher: PasswordHasher,
) -> Iterator[System]:
    _seed_node(node_settings, clock, hasher)
    _seed_hub(hub_settings, clock, hasher)
    with (
        TestClient(create_node(node_settings, clock=clock, llm=node_normalizer())) as node,
        TestClient(create_hub(hub_settings, clock=clock, llm=fake_llm())) as hub,
    ):
        system = System(node_settings, clock, node, hub)
        register_node_key(system)
        yield system


def _seed_node(settings: NodeSettings, clock: FakeClock, hasher: PasswordHasher) -> None:
    engine = make_engine(settings.database_url)
    NodeBase.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        seed_demo(session, hasher, settings, clock, llm=node_normalizer())
    engine.dispose()


def _seed_hub(settings: HubSettings, clock: FakeClock, hasher: PasswordHasher) -> None:
    engine = make_engine(settings.database_url)
    HubBase.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        seed_hub_demo(session, hasher, settings, clock, fake_llm())
    engine.dispose()
