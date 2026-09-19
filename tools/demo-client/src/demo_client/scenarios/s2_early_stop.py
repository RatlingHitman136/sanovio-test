"""Scenario 2 (§21): art_03 against BD Emerald™ Luer 10 ml, stopped by the connector."""

from demo_client.scenarios.common import (
    Actors,
    Purchase,
    ScenarioResult,
    open_assessment,
    print_round,
)

TITLE = "2 · early stop: art_03 vs BD Emerald™ Luer 10 ml (307736)"
EMERALD = "307736"


def run(actors: Actors) -> ScenarioResult:
    result = ScenarioResult(TITLE)
    console, hub = actors.console, actors.purchaser.hub
    purchase = Purchase.of(actors, "3")

    console.print(f"[bold]search[/bold] with {purchase.article['name']}")
    searched = purchase.search()
    listed = {c["article_no"] for c in searched["candidates"]}
    result.check("the search leaves Emerald out", EMERALD not in listed)
    result.check(
        "the connector filter is what excluded it",
        searched["excluded_by"].get("connector", 0) > 0,
        searched["excluded_by"],
    )

    # The purchaser opens it anyway, from the catalog: the hub has to say no on its own.
    emerald = next(v for v in hub.catalog_variants("Emerald") if v["article_no"] == EMERALD)
    console.print(f"[bold]assessment[/bold] against {emerald['display_name']}")
    detail = open_assessment(purchase, emerald["variant_id"])
    print_round(console, detail)
    result.check(
        "round 1 is NOT_EQUIVALENT",
        detail["rounds"][0]["rule_verdict"] == "NOT_EQUIVALENT",
        detail["rounds"][0]["rule_verdict"],
    )
    result.check("nobody is asked anything", not detail["questions"])
    if detail["status"] == "PROPOSED_RESOLUTION":
        hub.resolve(detail["id"], detail["proposed_verdict"], detail["version"])
    final = hub.assessment(detail["id"])
    result.check("the purchaser confirms it", final["status"] == "RESOLVED", final["status"])
    return result
