"""§21 scenario 7: a purchaser's free question becomes an attribute every hospital shares.

One node, as D55 keeps it: the second hospital exists only at the hub, so the checks after
approval (template sync, who gets asked) run on the ten_ksp node."""

from typing import Any

from demo_client.scenarios import s1_full_loop
from demo_client.scenarios.common import (
    Purchase,
    answer_purchaser,
    candidate,
    open_assessment,
    send_and_answer,
)
from e2e_system import System
from hub_fixtures import ART_03_LINKED, requirement

LABEL_QUESTION = "Enthält die Packung ein abziehbares Dokumentationsetikett?"
SPITAL2_ARTICLE = "ar_7W3K9Q2M5X8T"


def _plastipak_review(system: System) -> tuple[Purchase, Any]:
    """Scenario 1 up to question review, with the current product already marked."""
    actors = system.actors()
    purchase = Purchase.of(actors, "3")
    found = purchase.search()
    injekt, plastipak = candidate(found, "4606728V"), candidate(found, "300912")
    assert injekt and plastipak
    hub = actors.purchaser.hub
    actors.purchaser.node.set_reference(
        purchase.article["id"], hub.variant_attributes(injekt["variant_id"])
    )
    return purchase, open_assessment(purchase, plastipak["variant_id"])


def test_a_label_question_is_shared_then_approved_and_synced(system: System) -> None:
    purchase, review = _plastipak_review(system)
    actors = purchase.actors
    hub, operator = actors.purchaser.hub, actors.operator
    hub.add_question(review["id"], LABEL_QUESTION, review["version"])

    detail = answer_purchaser(purchase, hub.assessment(review["id"]), s1_full_loop.KNOWLEDGE)
    send_and_answer(actors, detail)

    [provisional] = operator.proposals("PROVISIONAL")
    assert provisional["attribute_key"] == "peel_off_label"

    # The other hospital sees BD's answer at once, as information only.
    spital2 = system.second_hospital()
    theirs = requirement(ART_03_LINKED, article_ref=SPITAL2_ARTICLE)
    plastipak = candidate(spital2.search(theirs, limit=50), "300912")
    assert plastipak is not None
    shown = plastipak["additional_information"]["peel_off_label"]["value"]
    assert shown == {"type": "bool", "value": True}
    assert all(p["attribute_key"] != "peel_off_label" for p in plastipak["precheck"])

    system.clock.advance(minutes=5)
    operator.approve_proposal(provisional["id"], "major", "exact")
    assert actors.purchaser.sync_templates() == ["syringe_single_use"]
    purchase.refresh()
    assert "peel_off_label" in purchase.article["unknown_attributes"]

    # BD's family answer stands: a new assessment asks the purchaser, never BD again.
    fresh = open_assessment(purchase, review["variant_id"])
    asked = {(q["addressee"], q["attribute_key"]) for q in fresh["questions"]}
    assert ("PURCHASER", "peel_off_label") in asked
    assert ("SUPPLIER", "peel_off_label") not in asked
