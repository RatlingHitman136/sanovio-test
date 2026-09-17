"""The egress log (N.7) and the per-user rate limits on it (D48).

Every requirement and every assertion is written here before it is handed to the client. A
refused issuance leaves an alert-only row, so bulk extraction attempts stay visible.
"""

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.hashing import sha256_hex
from hospital_node.core.settings import NodeSettings
from hospital_node.models import EgressLog, User
from hospital_node.models.exchange import EgressAlert, EgressKind
from hospital_node.services.errors import RateLimited

WINDOW = timedelta(hours=1)
ALERT_SHARE = 0.8


@dataclass(frozen=True)
class Limits:
    per_hour: int
    daily_alert: int


def limits_for(kind: EgressKind, settings: NodeSettings) -> Limits:
    per_hour = (
        settings.requirement_rate_limit_per_hour
        if kind is EgressKind.REQUIREMENT
        else settings.assertion_rate_limit_per_hour
    )
    return Limits(per_hour=per_hour, daily_alert=settings.egress_daily_alert_per_user)


def issue(
    session: Session,
    *,
    kind: EgressKind,
    user: User,
    content: dict[str, Any],
    limits: Limits,
    now: datetime,
    article_id: uuid.UUID | None = None,
    jti: str | None = None,
    kid: str | None = None,
) -> EgressLog:
    """Records what the node hands out, or refuses when the user is over their limit."""
    issued_last_hour = _count(session, user, kind, since=now - WINDOW)
    if issued_last_hour >= limits.per_hour:
        session.add(
            EgressLog(kind=kind, user_id=user.id, alert=EgressAlert.RATE_EXCEEDED, created_at=now)
        )
        # Committed on purpose: the refusal stays visible although the request itself fails.
        session.commit()
        raise RateLimited(
            f"limit of {limits.per_hour} {kind.lower()}s per hour reached",
            retry_after_s=_retry_after(session, user, kind, now),
        )
    row = EgressLog(
        kind=kind,
        article_id=article_id,
        user_id=user.id,
        content=content,
        content_sha256=sha256_hex(content),
        jti=jti,
        kid=kid,
        alert=_alert(session, user, kind, issued_last_hour, limits, now),
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def history(
    session: Session,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    article_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Sequence[EgressLog]:
    query = select(EgressLog).order_by(EgressLog.created_at.desc(), EgressLog.id.desc())
    if since is not None:
        query = query.where(EgressLog.created_at >= since)
    if until is not None:
        query = query.where(EgressLog.created_at <= until)
    if article_id is not None:
        query = query.where(EgressLog.article_id == article_id)
    if user_id is not None:
        query = query.where(EgressLog.user_id == user_id)
    return session.scalars(query).all()


def _alert(
    session: Session,
    user: User,
    kind: EgressKind,
    issued_last_hour: int,
    limits: Limits,
    now: datetime,
) -> str | None:
    today = _count(
        session,
        user,
        kind,
        since=now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0),
    )
    if today + 1 == limits.daily_alert:
        return EgressAlert.UNUSUAL_DAILY_VOLUME
    if issued_last_hour + 1 == math.ceil(ALERT_SHARE * limits.per_hour):
        return EgressAlert.RATE_80_PERCENT
    return None


def _count(session: Session, user: User, kind: EgressKind, *, since: datetime) -> int:
    rows = select(EgressLog).where(
        EgressLog.user_id == user.id,
        EgressLog.kind == kind,
        EgressLog.created_at >= since,
        # Refused attempts have no content and do not count against the limit.
        EgressLog.content.is_not(None),
    )
    return len(session.scalars(rows).all())


def _retry_after(session: Session, user: User, kind: EgressKind, now: datetime) -> int:
    oldest = session.scalars(
        select(EgressLog)
        .where(
            EgressLog.user_id == user.id,
            EgressLog.kind == kind,
            EgressLog.created_at >= now - WINDOW,
            EgressLog.content.is_not(None),
        )
        .order_by(EgressLog.created_at)
        .limit(1)
    ).first()
    if oldest is None:
        return int(WINDOW.total_seconds())
    return max(1, int((oldest.created_at + WINDOW - now).total_seconds()))
