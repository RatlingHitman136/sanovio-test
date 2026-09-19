"""Scenario 1 (§21): art_03 against BD Plastipak™ Luer-Lok™ 10 ml, the whole loop."""

from collections import Counter

from demo_client.scenarios.common import (
    Actors,
    Knowledge,
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

TITLE = "1 · full loop: art_03 vs BD Plastipak™ Luer-Lok™ 10 ml (300912)"

# What the purchaser knows about art_03 that its master data does not say.
KNOWLEDGE: Knowledge = {
    "single_use": {"type": "bool", "value": True},
    "standards": {"type": "list", "value": ["ISO 7886-1"]},
    "special_scale": {"type": "text", "value": "keine"},
    "needle_included": {"type": "bool", "value": False},
    "safety_mechanism": {"type": "bool", "value": False},
    "pump_compatible": {"type": "bool", "value": False},
    "light_protected": {"type": "bool", "value": False},
}


def run(actors: Actors) -> ScenarioResult:
    result = ScenarioResult(TITLE)
    console, hub, node = actors.console, actors.purchaser.hub, actors.purchaser.node
    before = egress_ids(actors)
    purchase = Purchase.of(actors, "3")

    console.print(f"[bold]search[/bold] with {purchase.article['name']}")
    first = purchase.search()
    injekt, plastipak = candidate(first, "4606728V"), candidate(first, "300912")
    if not result.check("the first search lists Injekt and Plastipak", bool(injekt and plastipak)):
        return result
    assert injekt is not None and plastipak is not None

    console.print(f"[bold]current product[/bold]: {injekt['display_name']}")
    unknown_before = len(purchase.article["unknown_attributes"])
    node.set_reference(purchase.article["id"], hub.variant_attributes(injekt["variant_id"]))
    purchase.refresh()
    filled = unknown_before - len(purchase.article["unknown_attributes"])
    result.check("marking the current product fills unknowns", filled > 0, f"{filled} filled")
    second = purchase.search()
    result.check(
        "the second search has more hard filters",
        len(second["search_spec"]["hard_filters"]) > len(first["search_spec"]["hard_filters"]),
    )

    console.print(f"[bold]assessment[/bold] against {plastipak['display_name']}")
    detail = open_assessment(purchase, plastipak["variant_id"])
    me = hub.me()
    hub.assign(detail["id"], me["subject_id"])
    print_round(console, detail)
    result.check(
        "round 1 asks for what is missing",
        detail["rounds"][0]["rule_verdict"] == "INSUFFICIENT_DATA",
        detail["rounds"][0]["rule_verdict"],
    )
    detail = drive(purchase, hub.assessment(detail["id"]), KNOWLEDGE)
    result.check(
        "the last round finds equivalence with deviations",
        detail["rounds"][-1]["rule_verdict"] == "EQUIVALENT_WITH_DEVIATIONS",
        detail["rounds"][-1]["rule_verdict"],
    )
    if detail["status"] == "PROPOSED_RESOLUTION":
        hub.resolve(detail["id"], detail["proposed_verdict"], detail["version"])
    final = hub.assessment(detail["id"])
    console.print(f"[bold]result[/bold]: {final['status']} · {final['final_verdict']}")
    result.check("the purchaser confirms it", final["status"] == "RESOLVED", final["status"])
    result.check(
        "the assessment is assigned to the purchaser",
        final["assigned_to_subject_id"] == me["subject_id"],
    )

    entries = new_egress(actors, before)
    kinds = Counter(entry["kind"] for entry in entries)
    result.check(
        "every requirement the scenario issued is in the egress log",
        kinds["REQUIREMENT"] == purchase.issued,
        dict(kinds),
    )
    found = leaked(purchase.article, entries)
    result.check("no name, brand, price or identifier left the node", not found, found or "")
    return result
