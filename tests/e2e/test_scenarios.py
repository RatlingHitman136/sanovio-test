"""§21 scenarios 1–4, run by the same code as `make demo SCENARIO=n` (§22 stage 6)."""

import pytest
from fastapi.testclient import TestClient

from demo_client.scenarios import SCENARIOS
from demo_client.scenarios.s4_identifiers import STERICAN
from e2e_system import System
from hospital_node.main import create_app as create_node
from node_fixtures import fake_normalizer as node_normalizer


@pytest.mark.parametrize("number", sorted(SCENARIOS))
def test_every_check_of_the_scenario_passes(system: System, number: int) -> None:
    result = SCENARIOS[number](system.actors())

    failed = [f"{check.name}: {check.detail}" for check in result.checks if not check.ok]
    assert not failed, failed
    assert result.checks


def test_scenario_4_with_product_hints_changes_no_verdict(system: System) -> None:
    """The re-run with SHARE_PRODUCT_HINTS=true (§21 scenario 4): the node restarts with hints
    on, the invalid GTIN is still withheld and the verdict is the one attributes gave."""
    assert SCENARIOS[4](system.actors()).ok
    hinted = system.node_settings.model_copy(update={"share_product_hints": True})

    with TestClient(create_node(hinted, clock=system.clock, llm=node_normalizer())) as node:
        purchaser = system.purchaser(node)
        art_06 = next(a for a in purchaser.node.articles() if a["internal_id"] == "6")
        requirement = purchaser.node.requirement(art_06["id"])["requirement"]
        found = purchaser.hub.search(requirement, limit=50)
        sterican = next(c for c in found["candidates"] if c["article_no"] == STERICAN)
        opened = purchaser.hub.open_assessment(requirement, sterican["variant_id"])
        round_one = purchaser.hub.settled(opened["id"])["rounds"][0]

    hints = requirement["product_hints"]
    assert hints["gtin"] is None  # the hospital's own GTIN fails its check digit
    assert hints["manufacturer_article_no"]  # sent, but it matches no B. Braun number
    assert sterican["identifier_match"] is None
    assert round_one["identifier_evidence"] == "NO_INFORMATION"
    assert round_one["rule_verdict"] == "EQUIVALENT"
