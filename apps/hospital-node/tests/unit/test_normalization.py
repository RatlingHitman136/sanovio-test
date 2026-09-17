import json
from typing import Any

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from equivalence_core.facts import HospitalSource
from hospital_node.core.security import PasswordHasher
from hospital_node.core.settings import NodeSettings
from hospital_node.main import create_app
from hospital_node.models import LlmCall, User
from hospital_node.models.articles import CategorySource, FactMethod
from hospital_node.services import normalization, template_sync
from hospital_node.services.normalization import NormalizationUnavailable
from llm_client import AnthropicClient
from node_fixtures import (
    FakeClock,
    article,
    fake_normalizer,
    load_fixture,
    login,
    names_in,
    seed_demo,
    values,
)

API_KEY = "sk-ant-api03-never-log-me"


def _calls(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(LlmCall)) or 0


def test_seed_matches_the_expected_facts_for_all_ten_articles(
    session: Session, hasher: PasswordHasher, llm_settings: NodeSettings, clock: FakeClock
) -> None:
    seed_demo(session, hasher, llm_settings, clock, fake_normalizer())

    for internal_id, expected in load_fixture("expected_facts.yaml").items():
        found = article(session, internal_id)
        assert found.category_code == expected["category"], internal_id
        assert found.category_source == expected["source"], internal_id
        assert values(found) == expected["attributes"], internal_id


def test_seed_makes_one_call_for_ten_articles(
    session: Session, hasher: PasswordHasher, llm_settings: NodeSettings, clock: FakeClock
) -> None:
    llm = fake_normalizer()

    seed_demo(session, hasher, llm_settings, clock, llm)

    assert len(llm.calls) == 1
    assert len(names_in(llm.calls[0])) == 10
    assert _calls(session) == 1


def test_batches_follow_the_batch_size(
    session: Session, hasher: PasswordHasher, llm_settings: NodeSettings, clock: FakeClock
) -> None:
    llm = fake_normalizer()

    seed_demo(
        session, hasher, llm_settings.model_copy(update={"normalize_batch_size": 4}), clock, llm
    )

    assert [len(names_in(call)) for call in llm.calls] == [4, 4, 2]


def test_parsers_win_and_the_model_fills_gaps(
    session: Session, hasher: PasswordHasher, llm_settings: NodeSettings, clock: FakeClock
) -> None:
    seed_demo(session, hasher, llm_settings, clock, fake_normalizer())
    syringe = article(session, "3")

    extracted = {
        fact.attribute_key: fact
        for fact in syringe.facts
        if fact.is_active and fact.source == HospitalSource.EXTRACTION
    }

    assert extracted["nominal_volume_ml"].method == FactMethod.RULES
    assert extracted["nominal_volume_ml"].raw_value == "10 ml"
    assert extracted["single_use"].method == FactMethod.LLM
    assert extracted["single_use"].llm_call_id is not None
    assert extracted["single_use"].prompt_version == "normalize_article_v1"
    assert str(extracted["single_use"].confidence) == "0.95"


def test_an_unchanged_restart_and_serving_requests_make_no_call(
    session: Session,
    hasher: PasswordHasher,
    llm_settings: NodeSettings,
    clock: FakeClock,
    engine: Engine,
) -> None:
    seed_demo(session, hasher, llm_settings, clock, fake_normalizer())
    anna = session.scalar(select(User).where(User.role == "PURCHASER"))
    assert anna is not None
    restarted = fake_normalizer()

    with TestClient(create_app(llm_settings, clock=clock, llm=restarted)) as client:
        headers = login(client, anna)
        client.get("/api/v1/auth/me", headers=headers)

    assert restarted.calls == []
    assert _calls(session) == 1


def test_a_changed_article_is_normalized_alone_at_startup(
    session: Session,
    hasher: PasswordHasher,
    llm_settings: NodeSettings,
    clock: FakeClock,
    engine: Engine,
) -> None:
    seed_demo(session, hasher, llm_settings, clock, fake_normalizer())
    needle = article(session, "6")
    # A new master record for the same article: same name, different yearly quantity.
    needle.raw = {**needle.raw, "Jahresmenge": "20000"}
    needle.content_hash = normalization.content_hash(needle)
    session.commit()
    restarted = fake_normalizer()

    with TestClient(create_app(llm_settings, clock=clock, llm=restarted)):
        pass

    assert [names_in(call) for call in restarted.calls] == [["Kanüle Sterican 0,8 × 40 mm"]]
    session.expire_all()
    assert values(article(session, "6"))["length_mm"] == 40
    # The earlier extraction facts were retracted, not duplicated.
    active = [
        f for f in article(session, "6").facts if f.is_active and f.attribute_key == "length_mm"
    ]
    assert len(active) == 1


def test_a_purchaser_category_survives_renormalization(
    session: Session, hasher: PasswordHasher, llm_settings: NodeSettings, clock: FakeClock
) -> None:
    seed_demo(session, hasher, llm_settings, clock, fake_normalizer())
    wipes = article(session, "7")
    wipes.category_code = "syringe_single_use"
    wipes.category_source = CategorySource.PURCHASER

    normalization.normalize(
        session,
        [wipes],
        templates=template_sync.installed(session),
        llm=fake_normalizer(),
        settings=llm_settings,
        now=clock(),
    )

    assert wipes.category_code == "syringe_single_use"
    assert wipes.category_source == CategorySource.PURCHASER


def test_rules_mode_needs_no_llm_and_logs_no_call(
    session: Session, hasher: PasswordHasher, settings: NodeSettings, clock: FakeClock
) -> None:
    seed_demo(session, hasher, settings, clock, llm=None)

    assert _calls(session) == 0
    assert article(session, "3").category_source == CategorySource.RULES
    assert normalization.stale_articles(session) == []


def test_llm_mode_without_a_key_refuses_to_normalize(
    session: Session, hasher: PasswordHasher, llm_settings: NodeSettings, clock: FakeClock
) -> None:
    with pytest.raises(NormalizationUnavailable, match="ANTHROPIC_API_KEY"):
        seed_demo(session, hasher, llm_settings, clock, llm=None)


def test_a_failed_call_keeps_rules_facts_and_leaves_articles_stale(
    session: Session, hasher: PasswordHasher, llm_settings: NodeSettings, clock: FakeClock
) -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        body = {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
        return httpx2.Response(529, json=body)

    seed_demo(session, hasher, llm_settings, clock, _anthropic(refuse))

    assert values(article(session, "3"))["connector"] == "LUER_LOCK"
    assert len(normalization.stale_articles(session)) == 10
    (call,) = session.scalars(select(LlmCall)).all()
    assert call.error is not None


def test_the_call_log_never_contains_the_key(
    session: Session, hasher: PasswordHasher, llm_settings: NodeSettings, clock: FakeClock
) -> None:
    readings = load_fixture("fake_llm_readings.yaml")
    sent: list[httpx2.Request] = []

    def answer(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        user_text = json.loads(request.content)["messages"][0]["content"]
        block = user_text.split("<articles>")[1].split("</articles>")[0]
        names = [entry["name"] for entry in json.loads(block)]
        batch = {"articles": [{"index": i, **readings[name]} for i, name in enumerate(names)]}
        return httpx2.Response(200, json=_message(json.dumps(batch)))

    seed_demo(session, hasher, llm_settings, clock, _anthropic(answer))

    (call,) = session.scalars(select(LlmCall)).all()
    assert call.error is None
    assert call.cost_usd is not None
    assert API_KEY not in json.dumps(call.request)
    assert sent[0].headers["x-api-key"] == API_KEY  # it was used, just never stored
    assert values(article(session, "1"))["latex_free"] is True


def _anthropic(handler: Any) -> AnthropicClient:
    sdk = anthropic.Anthropic(
        api_key=API_KEY,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        max_retries=0,
    )
    return AnthropicClient(SecretStr(API_KEY), sdk=sdk)


def _message(text: str) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1450, "output_tokens": 820},
    }
