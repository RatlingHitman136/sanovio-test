from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

from hospital_node import cli
from hospital_node.core.db import make_engine, make_session_factory
from hospital_node.models import HospitalArticle, LlmCall
from llm_client import FakeLLM
from node_fixtures import fake_normalizer

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    key = tmp_path / "node.pem"
    runner.invoke(cli.app, ["keygen", "--out", str(key), "--kid", "k"])
    return {
        "DATABASE_URL": f"sqlite:///{tmp_path / 'var' / 'node.db'}",
        "NODE_SIGNING_KEY_FILE": str(key),
        "NODE_SIGNING_KID": "k",
        "NORMALIZE_MODE": "llm",
        "NODE_SEED_PASSWORD": "correct horse battery",
    }


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeLLM]:
    llm = fake_normalizer()
    monkeypatch.setattr(cli, "llm_factory", lambda settings: llm)
    yield llm


def _count(env: dict[str, str], model: type) -> int:
    engine = make_engine(env["DATABASE_URL"])
    with make_session_factory(engine)() as session:
        count = session.scalar(select(func.count()).select_from(model)) or 0
    engine.dispose()
    return count


def test_seed_migrates_loads_and_normalizes(env: dict[str, str], fake: FakeLLM) -> None:
    result = runner.invoke(cli.app, ["seed"], env=env)

    assert result.exit_code == 0, result.output
    assert "seeded demo_ksp: 2 users, 10 articles" in result.output
    assert _count(env, HospitalArticle) == 10
    assert _count(env, LlmCall) == 1


def test_seed_needs_a_password(env: dict[str, str], fake: FakeLLM) -> None:
    result = runner.invoke(cli.app, ["seed"], env=env | {"NODE_SEED_PASSWORD": ""})

    assert result.exit_code == 1
    assert "NODE_SEED_PASSWORD" in result.output


def test_seed_refuses_existing_data_unless_reset(env: dict[str, str], fake: FakeLLM) -> None:
    runner.invoke(cli.app, ["seed"], env=env)

    again = runner.invoke(cli.app, ["seed"], env=env)
    reset = runner.invoke(cli.app, ["seed", "--reset"], env=env)

    assert again.exit_code == 1
    assert "already has data" in again.output
    assert reset.exit_code == 0, reset.output
    assert _count(env, HospitalArticle) == 10


def test_second_dataset_seeds(env: dict[str, str], fake: FakeLLM) -> None:
    result = runner.invoke(cli.app, ["seed", "--dataset", "demo_spital2"], env=env)

    assert result.exit_code == 0, result.output
    assert _count(env, HospitalArticle) == 2


def test_llm_mode_without_a_key_explains_itself(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "llm_factory", lambda settings: None)

    result = runner.invoke(cli.app, ["seed"], env=env)

    assert result.exit_code == 1
    assert "NORMALIZE_MODE=rules" in result.output


def test_migrate_and_create_user(env: dict[str, str]) -> None:
    assert runner.invoke(cli.app, ["migrate"], env=env).exit_code == 0

    created = runner.invoke(
        cli.app,
        ["create-user", "--email", "Bob@KSP.example", "--display-name", "Bob"],
        input="correct horse battery\ncorrect horse battery\n",
        env=env,
    )
    duplicate = runner.invoke(
        cli.app,
        ["create-user", "--email", "bob@ksp.example", "--display-name", "Bob"],
        input="correct horse battery\ncorrect horse battery\n",
        env=env,
    )

    assert created.exit_code == 0, created.output
    assert "created bob@ksp.example (PURCHASER)" in created.output
    assert duplicate.exit_code == 1
    assert "already exists" in duplicate.output
