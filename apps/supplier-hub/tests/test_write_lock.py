"""No job holds the database's write lock while a model thinks (found in the real-key run:
a 7-second Sonnet call behind a pending write made every request fail with "locked")."""

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from hub_fixtures import (
    ART_03_WITH_SCALE,
    FakeClock,
    Orgs,
    fetch,
    login,
    open_assessment,
    purchaser_headers,
    run_jobs,
    send_questions,
    supplier_answers,
)
from llm_client import LLMResult, StructuredRequest
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fakes import fake_llm
from supplier_hub.main import create_app
from supplier_hub.models import User
from supplier_hub.services.seed import SeedReport


class LockProbe:
    """Before each call, takes the write lock itself without waiting: it only gets it if no
    job is sitting on a pending write."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.inner = fake_llm()
        self.calls: list[str] = []

    def parse[T: BaseModel](self, request: StructuredRequest[T]) -> LLMResult[T]:
        probe = sqlite3.connect(self.database, timeout=0)
        try:
            probe.execute("BEGIN IMMEDIATE")  # raises "database is locked" if a writer waits
            probe.rollback()
        finally:
            probe.close()
        self.calls.append(request.purpose)
        return self.inner.parse(request)


def test_judge_proposal_and_extraction_calls_run_outside_any_write(
    settings: HubSettings, clock: FakeClock, orgs: Orgs, session: Session, seeded: SeedReport
) -> None:
    llm = LockProbe(Path(settings.database_url.removeprefix("sqlite:///")))
    with TestClient(create_app(settings, clock=clock, llm=llm)) as client:
        buyer = purchaser_headers(client, orgs, clock)
        created = open_assessment(client, buyer, session, "300912", ART_03_WITH_SCALE)
        run_jobs(client)
        review = fetch(client, buyer, created["id"])
        client.post(
            f"/api/v1/assessments/{created['id']}/questions",
            json={
                "version": review["version"],
                "addressee": "SUPPLIER",
                "attribute_key": None,
                "text": "Liegt der Packung ein abziehbares Dokumentationsetikett bei?",
            },
            headers=buyer,
        ).raise_for_status()
        run_jobs(client)
        send_questions(client, buyer, created["id"])
        bd_user = session.scalar(select(User).where(User.email == "catalog@bd-demo.example"))
        assert bd_user is not None
        bd = login(client, bd_user)
        typed = ART_03_WITH_SCALE | {"peel_off_label": {"type": "bool", "value": True}}
        comments = {"dehp_free": "Zylinder und Stopfen enthalten kein DEHP."}
        supplier_answers(client, bd, created["id"], typed, comments)
        run_jobs(client)
        final = fetch(client, buyer, created["id"])

    assert {"JUDGE", "PROPOSE_ATTRIBUTE", "EXTRACT_ANSWER"} <= set(llm.calls)
    assert final["status"] != "FAILED"
