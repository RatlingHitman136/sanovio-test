"""Ending an assessment, or reopening it (§11): confirm, override, decide, retry, cancel."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from hub_fixtures import (
    bare_assessment,
    fetch,
    open_assessment,
    run_jobs,
)
from supplier_hub.api.deps import HubContext
from supplier_hub.models import Assessment, Job
from supplier_hub.models.assessments import AssessmentStatus
from supplier_hub.services import assessment as assessments
from supplier_hub.services.seed import SeedReport


def _proposed(client: TestClient, buyer: dict[str, str], session: Session) -> Any:
    """Emerald: NOT_EQUIVALENT proposed after one round (scenario 2)."""
    created = open_assessment(client, buyer, session, "307736")
    run_jobs(client)
    return fetch(client, buyer, created["id"])


def _post(
    client: TestClient, buyer: dict[str, str], assessment: Any, action: str, **body: Any
) -> Any:
    return client.post(
        f"/api/v1/assessments/{assessment['id']}/{action}",
        json={"version": assessment["version"], **body},
        headers=buyer,
    )


def test_confirming_the_proposal(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    proposed = _proposed(client, buyer, session)

    response = _post(client, buyer, proposed, "resolve", verdict="NOT_EQUIVALENT")

    assert response.status_code == 200
    detail = client.get(f"/api/v1/assessments/{proposed['id']}", headers=buyer).json()
    assert (detail["status"], detail["final_verdict"], detail["resolution_kind"]) == (
        "RESOLVED",
        "NOT_EQUIVALENT",
        "CONFIRMED",
    )
    resolved = [e for e in detail["events"] if e["type"] == "RESOLVED"]
    assert resolved and resolved[0]["actor"] == detail["created_by_subject_id"]
    assert detail["resolved_by_subject_id"] == detail["created_by_subject_id"]


def test_overriding_needs_a_note(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    proposed = _proposed(client, buyer, session)

    without = _post(client, buyer, proposed, "resolve", verdict="EQUIVALENT")
    with_note = _post(
        client, buyer, proposed, "resolve", verdict="EQUIVALENT", note="Ward uses Luer adapters."
    )

    assert without.status_code == 422
    assert with_note.status_code == 200
    detail = client.get(f"/api/v1/assessments/{proposed['id']}", headers=buyer).json()
    assert (detail["resolution_kind"], detail["resolution_note"]) == (
        "OVERRIDDEN",
        "Ward uses Luer adapters.",
    )


def test_undetermined_is_not_an_override(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    proposed = _proposed(client, buyer, session)

    response = _post(client, buyer, proposed, "resolve", verdict="UNDETERMINED", note="?")

    assert response.status_code == 422


def test_a_resolved_assessment_is_final(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    proposed = _proposed(client, buyer, session)
    _post(client, buyer, proposed, "resolve", verdict="NOT_EQUIVALENT")
    after = client.get(f"/api/v1/assessments/{proposed['id']}", headers=buyer).json()

    assert _post(client, buyer, after, "cancel").status_code == 409
    assert _post(client, buyer, after, "request-more-info").status_code == 409


def test_asking_for_more_information_reopens_review(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    proposed = _proposed(client, buyer, session)

    response = _post(client, buyer, proposed, "request-more-info")

    assert response.status_code == 200
    assert response.json()["status"] == "NEEDS_QUESTION_REVIEW"
    assert response.json()["proposed_verdict"] is None


def test_a_stale_version_is_refused(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    proposed = _proposed(client, buyer, session)
    stale = proposed | {"version": proposed["version"] - 1}

    response = _post(client, buyer, stale, "resolve", verdict="NOT_EQUIVALENT")

    assert response.status_code == 409
    assert response.json()["code"] == "VERSION_CONFLICT"


def test_cancel(client: TestClient, buyer: dict[str, str], session: Session) -> None:
    proposed = _proposed(client, buyer, session)

    response = _post(client, buyer, proposed, "cancel")

    assert response.json()["status"] == "CANCELLED"


def _as_status(
    client: TestClient, buyer: dict[str, str], session: Session, status: AssessmentStatus
) -> Any:
    proposed = _proposed(client, buyer, session)
    row = session.scalar(select(Assessment).where(Assessment.id == uuid.UUID(proposed["id"])))
    assert row is not None
    row.status = status
    session.commit()
    return client.get(f"/api/v1/assessments/{proposed['id']}", headers=buyer).json()


def test_a_manual_decision_may_be_undetermined(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    waiting = _as_status(client, buyer, session, AssessmentStatus.NEEDS_MANUAL_DECISION)

    response = _post(client, buyer, waiting, "resolve", verdict="UNDETERMINED")

    assert response.status_code == 200
    detail = client.get(f"/api/v1/assessments/{waiting['id']}", headers=buyer).json()
    assert (detail["final_verdict"], detail["resolution_kind"]) == ("UNDETERMINED", "MANUAL")


def test_an_extra_round_reopens_question_review(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    waiting = _as_status(client, buyer, session, AssessmentStatus.NEEDS_MANUAL_DECISION)

    response = _post(client, buyer, waiting, "extra-round")

    assert response.json()["status"] == "NEEDS_QUESTION_REVIEW"


def test_a_failed_assessment_can_be_retried(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    failed = _as_status(client, buyer, session, AssessmentStatus.FAILED)

    response = _post(client, buyer, failed, "retry")

    assert response.json()["status"] == "ASSESSING"
    context: HubContext = client.app.state.hub  # type: ignore[attr-defined]
    assert context.run_jobs() == 1
    assert (
        client.get(f"/api/v1/assessments/{failed['id']}", headers=buyer).json()["current_round"]
        == 2
    )


def test_only_a_failed_assessment_can_be_retried(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    proposed = _proposed(client, buyer, session)

    assert _post(client, buyer, proposed, "retry").status_code == 409


def test_a_job_that_gives_up_fails_the_assessment(session: Session, seeded: SeedReport) -> None:
    row = bare_assessment(session)
    job = Job(kind="ASSESS", payload={"assessment_id": str(row.id)}, run_after=row.created_at)
    job.last_error = "APIConnectionError: timeout"

    assessments.give_up(session, job, row.created_at)

    assert row.status == AssessmentStatus.FAILED
