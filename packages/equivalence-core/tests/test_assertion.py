from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from equivalence_core.exchange.assertion import HubAssertion, issue_assertion

NOW = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
SUBJECT = "sub_7QF2M4XK9P3TZC8W1N6R"


def test_issued_assertion_follows_the_architecture() -> None:
    assertion = issue_assertion("ten_ksp", SUBJECT, "sanovio-hub", NOW)

    assert (assertion.iss, assertion.sub, assertion.aud, assertion.scope) == (
        "ten_ksp",
        SUBJECT,
        "sanovio-hub",
        "purchaser",
    )
    assert assertion.exp - assertion.iat == 300


def test_every_assertion_has_its_own_jti() -> None:
    jtis = {issue_assertion("ten_ksp", SUBJECT, "sanovio-hub", NOW).jti for _ in range(20)}
    assert len(jtis) == 20


@pytest.mark.parametrize("lifetime", [0, 301, 3600])
def test_lifetime_must_be_at_most_five_minutes(lifetime: int) -> None:
    with pytest.raises(ValidationError, match="expire within"):
        issue_assertion("ten_ksp", SUBJECT, "sanovio-hub", NOW, lifetime_seconds=lifetime)


def test_subject_must_be_a_pseudonym() -> None:
    with pytest.raises(ValidationError):
        HubAssertion(
            iss="ten_ksp",
            sub="anna.meier@demo-ksp.example",
            aud="sanovio-hub",
            iat=0,
            exp=60,
            jti="x",
        )
