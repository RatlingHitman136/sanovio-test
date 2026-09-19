"""Free text read by meaning before the judge (ARCHITECTURE §8): found in the dev data, where
the hospital's "nein" and BD's "keine" for special_scale came out as a mismatch."""

import json
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.facts import SupplierSource
from equivalence_core.values import TextValue
from hub_fixtures import (
    ART_03_LINKED,
    FakeClock,
    Orgs,
    fetch,
    open_assessment,
    purchaser_headers,
    run_jobs,
    variant,
)
from llm_client import FakeLLM
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm import compare_text, extract_answer, judge, normalize_item, propose_attribute
from supplier_hub.llm.fakes import fake_llm
from supplier_hub.llm.outputs import TextReading, TextReadings
from supplier_hub.main import create_app
from supplier_hub.models import LlmCall
from supplier_hub.services import catalog, projection, templates
from supplier_hub.services.seed import SeedReport


def _bd_says(session: Session, clock: FakeClock, scale: str) -> None:
    plastipak = variant(session, "300912")
    catalog.add_fact(
        session,
        key="special_scale",
        value=TextValue(value=scale),
        raw=scale,
        now=clock(),
        family_id=plastipak.family_id,
        source=SupplierSource.SUPPLIER_ANSWER,
    )
    template = templates.definition(session, "syringe_single_use")
    projection.rebuild_family(session, plastipak.family, template, now=clock())
    session.commit()


def _round_one(client: TestClient, buyer: dict[str, str], session: Session, ours: str) -> Any:
    requirement = ART_03_LINKED | {"special_scale": {"type": "text", "value": ours}}
    created = open_assessment(client, buyer, session, "300912", requirement)
    run_jobs(client)
    judgments = fetch(client, buyer, created["id"])["rounds"][0]["attribute_judgments"]
    return next(j for j in judgments if j["attribute_key"] == "special_scale")


def _calls(session: Session, purpose: str) -> int:
    session.expire_all()
    return len(session.scalars(select(LlmCall).where(LlmCall.purpose == purpose)).all())


def test_nein_and_keine_match_without_any_model(
    client: TestClient, buyer: dict[str, str], session: Session, clock: FakeClock
) -> None:
    _bd_says(session, clock, "keine")

    scale = _round_one(client, buyer, session, "nein")

    assert (scale["status"], scale["decided_by"]) == ("MATCH", "COMPARATOR")
    assert _calls(session, compare_text.PURPOSE) == 0


def test_a_rewording_is_read_by_one_small_call(
    client: TestClient, buyer: dict[str, str], session: Session, clock: FakeClock
) -> None:
    _bd_says(session, clock, "0,2 ml Skala")

    scale = _round_one(client, buyer, session, "Skala in 0,2 ml Schritten")

    assert (scale["status"], scale["decided_by"]) == ("MATCH", "LLM")
    assert scale["rationale"]
    assert _calls(session, compare_text.PURPOSE) == 1
    [call] = session.scalars(select(LlmCall).where(LlmCall.purpose == compare_text.PURPOSE))
    assert (call.model, call.effort) == ("claude-haiku-4-5", None)
    assert call.assessment_id is not None


def test_what_the_small_model_cannot_tell_goes_to_the_judge(
    settings: HubSettings,
    clock: FakeClock,
    orgs: Orgs,
    session: Session,
    seeded: SeedReport,
) -> None:
    base = fake_llm()

    def unsure(request: Any) -> TextReadings:
        pairs = _pairs(request)
        return TextReadings(
            readings=[
                TextReading(attribute_key=key, status="UNKNOWN", rationale="Too vague.")
                for key in pairs
            ]
        )

    def via(request: Any) -> Any:
        return base.parse(request).output

    purposes = (
        normalize_item.PURPOSE,
        judge.PURPOSE,
        extract_answer.PURPOSE,
        propose_attribute.PURPOSE,
    )
    llm = FakeLLM({purpose: via for purpose in purposes} | {compare_text.PURPOSE: unsure})
    _bd_says(session, clock, "0,2 ml Skala")
    with TestClient(create_app(settings, clock=clock, llm=llm)) as client:
        buyer = purchaser_headers(client, orgs, clock)
        scale = _round_one(client, buyer, session, "Skala in 0,2 ml Schritten")

    # The judge had it: decided by the model, but in the judge's words, not Haiku's.
    assert scale["decided_by"] == "LLM"
    assert scale["rationale"] != "Too vague."
    judged = [request.purpose for request in llm.calls]
    assert judged.index(compare_text.PURPOSE) < judged.index(judge.PURPOSE)


def _pairs(request: Any) -> list[str]:
    data = json.loads(request.user.split("<data>")[1].split("</data>")[0])
    return [pair["attribute_key"] for pair in data["pairs"]]
