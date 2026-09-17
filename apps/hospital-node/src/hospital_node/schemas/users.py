from pydantic import BaseModel

from hospital_node.models.users import Role


class UserEntry(BaseModel):
    """What the client needs to show a hub subject by name; no email, no internal id."""

    display_name: str
    role: Role
    hub_subject_id: str
    is_active: bool
