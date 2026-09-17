"""Signs the short-lived assertion a purchaser exchanges for a hub token (ARCHITECTURE §17)."""

from datetime import datetime
from typing import Any

from equivalence_core.exchange.assertion import ASSERTION_TYP, issue_assertion
from equivalence_core.exchange.jws import sign
from hospital_node.core.secrets import NodeSecrets
from hospital_node.core.settings import NodeSettings
from hospital_node.models import User


def sign_assertion(
    secrets: NodeSecrets, settings: NodeSettings, user: User, now: datetime
) -> tuple[str, dict[str, Any]]:
    """(token, claims). Only the claims are logged; the token itself never is."""
    claims = issue_assertion(
        tenant=settings.node_tenant_id,
        subject=user.hub_subject_id,
        audience=settings.hub_audience,
        now=now,
    )
    token = sign(
        claims.model_dump(), secrets.signing_key, kid=secrets.signing_kid, typ=ASSERTION_TYP
    )
    return token, claims.model_dump()
