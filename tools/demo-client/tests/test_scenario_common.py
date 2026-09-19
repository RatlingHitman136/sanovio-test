from demo_client.scenarios import SCENARIOS
from demo_client.scenarios.common import ScenarioResult, candidate, drafts, leaked

ARTICLE = {
    "name": "Einmalspritze 10 ml Luer-Lock steril",
    "brand": "B. Braun",
    "target_net_price": "0.12",
    "identifiers": [{"scheme": "GTIN", "value": "04022495123456"}],
}


def test_a_result_fails_when_any_check_fails() -> None:
    result = ScenarioResult("x")
    result.check("first", True)
    assert result.ok
    result.check("second", False, 3)
    assert not result.ok
    assert result.checks[1].detail == "3"


def test_the_leak_check_reads_what_the_egress_log_recorded() -> None:
    clean = [{"content": {"attributes": {"nominal_volume_ml": 10}}}]
    dirty = clean + [{"content": {"product_hints": {"gtin": "04022495123456"}}}]

    assert leaked(ARTICLE, clean) == []
    assert leaked(ARTICLE, dirty) == ["04022495123456"]
    # An assertion's egress row has no content; it cannot leak anything.
    assert leaked(ARTICLE, [{"content": None}]) == []


def test_drafts_and_candidates_are_picked_by_their_keys() -> None:
    detail = {
        "questions": [
            {"addressee": "SUPPLIER", "status": "DRAFT", "attribute_key": "mdr_class"},
            {"addressee": "SUPPLIER", "status": "SENT", "attribute_key": "dehp_free"},
            {"addressee": "PURCHASER", "status": "DRAFT", "attribute_key": "wall_type"},
        ]
    }
    assert [q["attribute_key"] for q in drafts(detail, "SUPPLIER")] == ["mdr_class"]
    result = {"candidates": [{"article_no": "300912"}]}
    assert candidate(result, "300912") == {"article_no": "300912"}
    assert candidate(result, "307736") is None


def test_the_demo_offers_scenarios_one_to_four() -> None:
    assert sorted(SCENARIOS) == [1, 2, 3, 4]
