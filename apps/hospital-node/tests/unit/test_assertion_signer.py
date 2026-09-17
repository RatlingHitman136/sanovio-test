from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from equivalence_core.exchange.assertion import ASSERTION_TYP
from equivalence_core.exchange.jws import JwsError, verify
from equivalence_core.exchange.keys import load_private_key
from hospital_node.core.secrets import load_node_secrets
from hospital_node.core.settings import NodeSettings
from hospital_node.models.users import Role
from hospital_node.services.assertion_signer import sign_assertion
from hospital_node.services.seed import SeedReport
from node_fixtures import FakeClock, user


def test_the_assertion_verifies_against_the_public_key(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    anna = user(session, Role.PURCHASER)
    public = load_private_key(settings.node_signing_key_file).public_key()

    token, claims = sign_assertion(load_node_secrets(settings), settings, anna, clock())

    verified = verify(
        token,
        typ=ASSERTION_TYP,
        audience="sanovio-hub",
        key_lookup=lambda issuer, kid: public if (issuer, kid) == ("ten_ksp", "test-kid") else None,
        now=clock(),
    )
    assert verified["sub"] == anna.hub_subject_id
    assert verified["scope"] == "purchaser"
    assert verified["exp"] - verified["iat"] == 300
    assert claims["jti"] == verified["jti"]
    assert datetime.fromtimestamp(verified["iat"], tz=UTC) == clock()


def test_another_issuers_key_is_not_accepted(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    anna = user(session, Role.PURCHASER)
    token, _ = sign_assertion(load_node_secrets(settings), settings, anna, clock())

    with pytest.raises(JwsError):
        verify(
            token,
            typ=ASSERTION_TYP,
            audience="sanovio-hub",
            key_lookup=lambda issuer, kid: None,
            now=clock(),
        )
