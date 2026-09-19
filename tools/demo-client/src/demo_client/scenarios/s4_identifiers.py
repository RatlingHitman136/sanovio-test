"""Scenario 4 (§21): art_06 against B. Braun Sterican® 21 G × 1½", with unreliable identifiers.

The hints-on re-run needs a node restarted with SHARE_PRODUCT_HINTS=true; the e2e suite does
it in-process, and by hand it is: set the variable in the node's .env, restart it, run again.
"""

from typing import Any

from demo_client.scenarios.common import (
    Actors,
    Purchase,
    ScenarioResult,
    candidate,
    drive,
    egress_ids,
    leaked,
    new_egress,
    open_assessment,
    print_round,
)
from demo_client.scenarios.s3_manual_decision import KNOWLEDGE

TITLE = '4 · unreliable identifiers: art_06 vs B. Braun Sterican® 21 G × 1½" (4657527B)'
STERICAN = "4657527B"
GTIN_QUESTION = "Wie lautet die GTIN der Handelseinheit?"


def run(actors: Actors) -> ScenarioResult:
    result = ScenarioResult(TITLE)
    console, hub = actors.console, actors.purchaser.hub
    before = egress_ids(actors)
    purchase = Purchase.of(actors, "6")

    issues = purchase.article["data_quality_issues"]
    console.print(f"[bold]node warnings[/bold] for {purchase.article['name']}: {issues}")
    result.check("the node flags the article's identifiers", bool(issues), issues)

    searched = purchase.search()
    sterican = candidate(searched, STERICAN)
    if not result.check("Sterican is found by its attributes alone", sterican is not None):
        return result
    assert sterican is not None
    result.check("no identifier matched anything", sterican["identifier_match"] is None)

    console.print(f"[bold]assessment[/bold] against {sterican['display_name']}")
    detail = open_assessment(purchase, sterican["variant_id"])
    print_round(console, detail)

    def ask_for_the_gtin(review: dict[str, Any]) -> None:
        console.print(f"  purchaser adds: {GTIN_QUESTION}")
        hub.add_question(review["id"], GTIN_QUESTION, review["version"])

    detail = drive(purchase, hub.assessment(detail["id"]), KNOWLEDGE, in_review=ask_for_the_gtin)
    last = detail["rounds"][-1]["rule_verdict"]
    result.check("the last round finds them equivalent", last == "EQUIVALENT", last)

    routed = [p for p in actors.operator.proposals("ROUTED") if p["question_text"] == GTIN_QUESTION]
    result.check("the GTIN question became an identifier question", bool(routed))
    identifiers = hub.variant_attributes(sterican["variant_id"])["identifiers"]
    result.check(
        "B. Braun's GTIN is stored as an identifier, not an attribute",
        any(entry["scheme"] == "GTIN" for entry in identifiers),
        identifiers,
    )
    if detail["status"] == "PROPOSED_RESOLUTION":
        hub.resolve(detail["id"], detail["proposed_verdict"], detail["version"])
    final = hub.assessment(detail["id"])
    console.print(f"[bold]result[/bold]: {final['status']} · {final['final_verdict']}")
    result.check("the purchaser confirms it", final["status"] == "RESOLVED", final["status"])

    found = leaked(purchase.article, new_egress(actors, before))
    result.check("no identifier left the node (hints off)", not found, found or "")
    return result
