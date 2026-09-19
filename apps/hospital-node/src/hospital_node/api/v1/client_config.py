"""What the purchaser app needs before anyone signs in (ARCHITECTURE §20)."""

from fastapi import APIRouter
from pydantic import BaseModel

from hospital_node.api.deps import Context

router = APIRouter(tags=["client"])


class ClientConfig(BaseModel):
    # Where the browser reaches the hub; the node itself never calls it (D33).
    hub_url: str


@router.get("/client-config")
def client_config(context: Context) -> ClientConfig:
    return ClientConfig(hub_url=context.settings.hub_url)
