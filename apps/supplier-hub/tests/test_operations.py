"""Keeping the hub running without seeing hospital data: jobs, LLM spend, counts, catalogs
(§17.1, D58)."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from hub_fixtures import FakeClock, bare_assessment, variant
from supplier_hub.models import Job, LlmCall
from supplier_hub.models.jobs import JobKind, JobStatus

ADMIN = "/api/v1/admin"


def _failed_job(session: Session, kind: JobKind, payload: dict[str, str], clock: FakeClock) -> Job:
    job = Job(
        kind=kind,
        payload=payload,
        status=JobStatus.FAILED,
        attempts=3,
        run_after=clock(),
        finished_at=clock(),
        last_error="RuntimeError: normalize_item failed",
    )
    session.add(job)
    session.commit()
    return job


def test_a_failed_catalog_reading_is_retried_with_fresh_attempts(
    client: TestClient, operator: dict[str, str], session: Session, clock: FakeClock
) -> None:
    family_id = str(variant(session, "300912").family_id)
    job = _failed_job(session, JobKind.NORMALIZE_ITEM, {"family_id": family_id}, clock)
    [listed] = client.get(f"{ADMIN}/jobs", params={"status": "FAILED"}, headers=operator).json()
    assert (listed["retryable"], listed["last_error"]) == (True, "RuntimeError")

    retried = client.post(f"{ADMIN}/jobs/{job.id}/retry", headers=operator)

    assert retried.status_code == 200, retried.text
    assert (retried.json()["status"], retried.json()["attempts"]) == ("QUEUED", 0)


def test_an_assessment_job_is_left_to_the_hospital(
    client: TestClient, operator: dict[str, str], session: Session, clock: FakeClock
) -> None:
    job = _failed_job(session, JobKind.ASSESS, {"assessment_id": "a", "round_no": "1"}, clock)
    [listed] = client.get(f"{ADMIN}/jobs", headers=operator).json()
    assert not listed["retryable"]

    response = client.post(f"{ADMIN}/jobs/{job.id}/retry", headers=operator)

    assert response.status_code == 409
    assert response.json()["code"] == "JOB_BELONGS_TO_ASSESSMENT"


def test_llm_usage_adds_up_without_prompts_or_answers(
    client: TestClient, operator: dict[str, str], session: Session
) -> None:
    calls = session.scalars(select(LlmCall)).all()
    assert calls, "the seed reads the catalogs with the fake model"

    response = client.get(f"{ADMIN}/llm-usage", params={"days": 30}, headers=operator)

    rows = response.json()
    assert sum(row["calls"] for row in rows) == len(calls)
    assert sum(row["input_tokens"] for row in rows) == sum(call.input_tokens for call in calls)
    assert sum(Decimal(row["cost_usd"]) for row in rows) == sum(
        (call.cost_usd or Decimal(0) for call in calls), Decimal(0)
    )
    assert all("request" not in row and "response" not in row for row in rows)


def test_a_failed_call_shows_only_the_kind_of_failure(
    client: TestClient, operator: dict[str, str], session: Session, clock: FakeClock
) -> None:
    session.add(
        LlmCall(
            purpose="JUDGE",
            model="claude-opus-5",
            prompt_version="judge_v1",
            request={"user": "Heparin-Skala: nein"},
            input_tokens=10,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            latency_ms=900,
            error="invalid output: 1 validation error, input_value='nein'",
            created_at=clock(),
        )
    )
    session.commit()

    response = client.get(f"{ADMIN}/llm-usage/failures", headers=operator)

    [failure] = response.json()
    assert (failure["purpose"], failure["error_kind"]) == ("JUDGE", "invalid output")
    assert "nein" not in response.text


def test_assessment_counts_name_no_article(
    client: TestClient, operator: dict[str, str], session: Session
) -> None:
    bare_assessment(session)
    session.commit()

    response = client.get(f"{ADMIN}/stats/assessments", headers=operator)

    assert response.json() == [
        {"tenant_code": "ten_ksp", "by_status": {"ASSESSING": 1}, "by_verdict": {}}
    ]
    assert "ar_" not in response.text


def test_every_catalog_is_readable_and_can_be_read_again(
    client: TestClient, operator: dict[str, str], session: Session
) -> None:
    families = client.get(f"{ADMIN}/catalog/families", headers=operator).json()
    assert {family["supplier"] for family in families} >= {"BD", "B. Braun"}
    plastipak = str(variant(session, "300912").family_id)

    detail = client.get(f"{ADMIN}/catalog/families/{plastipak}", headers=operator)
    assert detail.status_code == 200
    assert detail.json()["variants"]

    queued = client.post(f"{ADMIN}/catalog/families/{plastipak}/normalize", headers=operator)
    assert queued.json()["status"] == "QUEUED"
    again = client.post(f"{ADMIN}/catalog/families/{plastipak}/normalize", headers=operator)
    assert again.status_code == 409
