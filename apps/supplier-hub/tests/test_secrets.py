"""The Anthropic key reaches Anthropic and nothing else: no table, no response, no log."""

import json
import logging
from typing import Any

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from hub_fixtures import FakeClock, Orgs, open_assessment, purchaser_headers, run_jobs
from llm_client import AnthropicClient
from supplier_hub.core.settings import HubSettings
from supplier_hub.main import create_app
from supplier_hub.models import Job, LlmCall
from supplier_hub.services.seed import SeedReport

API_KEY = "sk-ant-api03-never-log-me"


def test_a_failing_judge_call_leaves_no_trace_of_the_key(
    settings: HubSettings,
    clock: FakeClock,
    orgs: Orgs,
    session: Session,
    seeded: SeedReport,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sent: list[httpx2.Request] = []

    def refuse(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        error = {"type": "authentication_error", "message": "invalid x-api-key"}
        return httpx2.Response(401, json={"type": "error", "error": error})

    sdk = anthropic.Anthropic(
        api_key=API_KEY,
        http_client=httpx2.Client(transport=httpx2.MockTransport(refuse)),
        max_retries=0,
    )
    llm = AnthropicClient(SecretStr(API_KEY), sdk=sdk)
    caplog.set_level(logging.DEBUG)

    with TestClient(create_app(settings, clock=clock, llm=llm)) as client:
        buyer = purchaser_headers(client, orgs, clock)
        created = open_assessment(client, buyer, session, "300912")
        run_jobs(client)
        responses = [
            client.get(f"/api/v1/assessments/{created['id']}", headers=buyer).text,
            client.get("/api/v1/assessments", headers=buyer).text,
        ]

    assert sent and sent[0].headers["x-api-key"] == API_KEY  # used, and only there
    calls = session.scalars(select(LlmCall)).all()
    assert calls and all(call.error for call in calls if call.purpose == "JUDGE")
    stored: list[Any] = [(c.request, c.response, c.error) for c in calls]
    stored += [(j.payload, j.last_error) for j in session.scalars(select(Job))]
    for text in (json.dumps(stored, default=str), *responses, caplog.text):
        assert API_KEY not in text
