from fastapi import APIRouter

from hospital_node.api.deps import AnyNodeUser, DbSession
from hospital_node.models.users import Role
from hospital_node.schemas.users import UserEntry
from hospital_node.services.user_directory import list_users

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def users(session: DbSession, _: AnyNodeUser, include_inactive: bool = False) -> list[UserEntry]:
    return [
        UserEntry(
            display_name=user.display_name,
            role=Role(user.role),
            hub_subject_id=user.hub_subject_id,
            is_active=user.is_active,
        )
        for user in list_users(session, include_inactive=include_inactive)
    ]
