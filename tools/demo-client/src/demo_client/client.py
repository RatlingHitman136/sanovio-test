"""Calls the node and hub APIs; the HTTP client is injected so tests can fake the network."""

from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from equivalence_core.service_info import ServiceHealth


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    base_url: str
    up: bool
    detail: str


def check_health(http: httpx.Client, name: str, base_url: str) -> ServiceStatus:
    try:
        response = http.get(f"{base_url}/api/v1/health")
        response.raise_for_status()
        health = ServiceHealth.model_validate(response.json())
    except (httpx.HTTPError, ValueError, ValidationError) as exc:
        return ServiceStatus(name, base_url, up=False, detail=str(exc))
    return ServiceStatus(name, base_url, up=True, detail=f"{health.service} {health.version}")
