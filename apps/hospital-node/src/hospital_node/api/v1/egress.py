import uuid
from collections import Counter
from datetime import datetime

from fastapi import APIRouter

from hospital_node.api.deps import DbSession, NodeAdmin
from hospital_node.models.exchange import EgressKind
from hospital_node.schemas.exchange import EgressEntry, EgressPage
from hospital_node.services import egress_log

router = APIRouter(prefix="/egress", tags=["exchange"])


@router.get("")
def read_egress(
    session: DbSession,
    _: NodeAdmin,
    from_: datetime | None = None,
    to: datetime | None = None,
    article_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> EgressPage:
    """What this node issued for the hub, with per-user counts and alerts (D48)."""
    rows = egress_log.history(
        session, since=from_, until=to, article_id=article_id, user_id=user_id
    )
    issued = Counter(row.user.display_name for row in rows if row.issued)
    return EgressPage(
        entries=[
            EgressEntry(
                id=row.id,
                kind=EgressKind(row.kind),
                created_at=row.created_at,
                user=row.user.display_name,
                article_id=row.article_id,
                content=row.content,
                content_sha256=row.content_sha256,
                jti=row.jti,
                alert=row.alert,
            )
            for row in rows
        ],
        issued_per_user=dict(issued),
        alerts=sum(row.alert is not None for row in rows),
    )
