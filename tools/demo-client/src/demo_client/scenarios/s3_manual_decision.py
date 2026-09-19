"""Scenario 3 (§21): art_06 against BD Microlance™ 21 G 1½", ending with a person's decision."""

from demo_client.scenarios.common import (
    Actors,
    Knowledge,
    Purchase,
    ScenarioResult,
    candidate,
    drive,
    open_assessment,
    print_round,
)

TITLE = '3 · manual decision: art_06 vs BD Microlance™ 21 G 1½" (304432)'

# What the purchaser knows about their current needle (a Sterican® 0.8 × 40 mm) that the
# node could not read from its name. Scenario 4 uses the same article.
KNOWLEDGE: Knowledge = {
    "sterile": {"type": "bool", "value": True},
    "single_use": {"type": "bool", "value": True},
    "latex_free": {"type": "bool", "value": True},
    "dehp_free": {"type": "bool", "value": True},
    "standards": {"type": "list", "value": ["ISO 7864"]},
    "inner_diameter_mm": {"type": "number", "value": 0.58, "unit": "mm"},
    "wall_type": {"type": "enum", "value": "REGULAR"},
    "bevel": {"type": "enum", "value": "LONG"},
    "purpose": {"type": "enum", "value": "INJECTION"},
    "filter_um": {"type": "number", "value": 0, "unit": "µm"},
    "safety_mechanism": {"type": "bool", "value": False},
    "connector": {"type": "enum", "value": "LUER"},
    "iso_7864_compliant": {"type": "bool", "value": True},
}


def run(actors: Actors) -> ScenarioResult:
    result = ScenarioResult(TITLE)
    console, hub = actors.console, actors.purchaser.hub
    purchase = Purchase.of(actors, "6")

    console.print(f"[bold]search[/bold] with {purchase.article['name']}")
    microlance = candidate(purchase.search(), "304432")
    if not result.check("the search lists Microlance", microlance is not None):
        return result
    assert microlance is not None

    console.print(f"[bold]assessment[/bold] against {microlance['display_name']}")
    detail = open_assessment(purchase, microlance["variant_id"])
    print_round(console, detail)
    asked = {q["attribute_key"] for q in detail["questions"] if q["addressee"] == "PURCHASER"}
    result.check("the purchaser is asked for the wall type", "wall_type" in asked, sorted(asked))
    detail = drive(purchase, hub.assessment(detail["id"]), KNOWLEDGE)
    result.check(
        "the loop stops for a person",
        detail["status"] == "NEEDS_MANUAL_DECISION",
        f"{detail['status']} ({detail['manual_reason']})",
    )
    result.check(
        "because a blocking gap cannot be closed",
        detail["manual_reason"] == "BLOCKING_UNAVAILABLE",
        detail["manual_reason"],
    )
    unavailable = {q["attribute_key"] for q in detail["questions"] if q["status"] == "UNAVAILABLE"}
    result.check(
        "BD cannot provide the inner diameter",
        "inner_diameter_mm" in unavailable,
        sorted(unavailable),
    )
    if detail["status"] == "NEEDS_MANUAL_DECISION":
        hub.resolve(
            detail["id"],
            "NOT_EQUIVALENT",
            detail["version"],
            note="Thin wall and no inner diameter: not accepted without a trial.",
        )
    final = hub.assessment(detail["id"])
    console.print(f"[bold]result[/bold]: {final['status']} · {final['final_verdict']}")
    result.check(
        "the purchaser decides it manually",
        (final["status"], final["resolution_kind"]) == ("RESOLVED", "MANUAL"),
        f"{final['status']} · {final['resolution_kind']}",
    )
    return result
