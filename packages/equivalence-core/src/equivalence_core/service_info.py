"""The health response shared by both services and read by the demo client."""

from typing import Literal

from pydantic import BaseModel


class ServiceHealth(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
