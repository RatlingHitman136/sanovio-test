from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hub_fixtures import Orgs
from supplier_hub.models import ApiToken, TenantSigningKey
from supplier_hub.models.identity import UserRole

NOW = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
PUBLIC_JWK = {"kty": "OKP", "crv": "Ed25519", "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"}


def test_a_private_key_can_never_be_stored(session: Session, orgs: Orgs) -> None:
    tenant = orgs.hospital()
    operator = orgs.user(orgs.operator(), "ops@sanovio-demo.example", UserRole.OPERATOR)
    session.add(
        TenantSigningKey(
            tenant_id=tenant.id,
            kid="ksp-2026-09",
            public_jwk=PUBLIC_JWK | {"d": "a-private-key"},
            fingerprint="0" * 64,
            not_before=NOW,
            registered_by=operator.id,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_token_belongs_to_exactly_one_owner(session: Session, orgs: Orgs) -> None:
    supplier_user = orgs.user(orgs.supplier(), "catalog@bd-demo.example", UserRole.SUPPLIER)
    session.add(ApiToken(token_hash="a" * 64, expires_at=NOW))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    session.add(ApiToken(user_id=supplier_user.id, token_hash="b" * 64, expires_at=NOW))
    session.flush()
