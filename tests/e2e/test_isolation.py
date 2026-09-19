"""§21 scenario 6: security and isolation across node, client and hub, no LLM involved."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from demo_client.api import ApiError
from demo_client.hub import HubClient
from e2e_system import BASE_URL, System
from hospital_node.main import create_app as create_node
from node_fixtures import fake_normalizer as node_normalizer


def _art_03(system: System) -> tuple[Any, dict[str, Any]]:
    purchaser = system.purchaser()
    article = next(a for a in purchaser.node.articles() if a["internal_id"] == "3")
    return purchaser, purchaser.node.requirement(article["id"])["requirement"]


def _refused(call: Any) -> int:
    with pytest.raises(ApiError) as refused:
        call()
    return refused.value.status


def test_a_requirement_with_anything_extra_is_refused(system: System) -> None:
    purchaser, requirement = _art_03(system)

    for tampered in (
        requirement | {"name": "Einmalspritze 10 ml Luer-Lock steril"},
        requirement | {"target_net_price": "0.12"},
        requirement | {"template_code": "no_such_template"},
    ):
        assert _refused(lambda body=tampered: purchaser.hub.search(body)) == 422


def test_another_hospital_never_reaches_this_one(system: System) -> None:
    purchaser, requirement = _art_03(system)
    plastipak = next(
        c for c in purchaser.hub.search(requirement)["candidates"] if c["article_no"] == "300912"
    )
    ours = purchaser.hub.open_assessment(requirement, plastipak["variant_id"])
    spital2 = system.second_hospital()

    assert _refused(lambda: spital2.assessment(ours["id"])) == 404
    # Posting ten_ksp's article_ref only ever creates spital2's own assessment.
    theirs = spital2.open_assessment(requirement, plastipak["variant_id"])
    assert [a["id"] for a in spital2.assessments()] == [theirs["id"]]
    assert [a["id"] for a in purchaser.hub.assessments()] == [ours["id"]]


def test_assertions_are_single_use_and_short_lived(system: System) -> None:
    purchaser = system.purchaser()
    hub = HubClient(system.hub, BASE_URL)
    assertion = purchaser.node.assertion()["assertion"]
    hub.exchange(assertion)

    assert _refused(lambda: hub.exchange(assertion)) == 401
    late = purchaser.node.assertion()["assertion"]
    system.clock.advance(minutes=10)
    assert _refused(lambda: hub.exchange(late)) == 401


def test_an_expired_hub_session_is_renewed_silently(system: System) -> None:
    purchaser = system.purchaser()
    first = purchaser.hub.token
    system.clock.advance(minutes=31)

    assert purchaser.hub.me()["kind"] == "purchaser"
    assert purchaser.hub.token != first


def test_revoking_a_key_ends_its_sessions(system: System) -> None:
    purchaser = system.purchaser()
    purchaser.hub.reauthenticate = None  # observe the refusal instead of renewing
    operator = system.operator()
    tenant = next(t for t in operator.tenants() if t["code"] == "ten_ksp")

    operator.revoke_key(tenant["id"], system.node_settings.node_signing_kid)

    assert _refused(purchaser.hub.me) == 401
    fresh = purchaser.node.assertion()["assertion"]
    assert _refused(lambda: purchaser.hub.exchange(fresh)) == 401


def test_the_node_limits_requirements_and_raises_an_alert(system: System) -> None:
    limited = system.node_settings.model_copy(update={"requirement_rate_limit_per_hour": 5})
    with TestClient(create_node(limited, clock=system.clock, llm=node_normalizer())) as node:
        purchaser = system.purchaser(node)
        article = next(a for a in purchaser.node.articles() if a["internal_id"] == "3")
        statuses = [purchaser.node.requirement_status(article["id"]) for _ in range(6)]
        log = system.node_admin().egress()

    assert statuses == [200] * 5 + [429]
    assert log["alerts"] >= 1
