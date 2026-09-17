from importlib.metadata import version

from fastapi import APIRouter

from equivalence_core.service_info import ServiceHealth

SERVICE_NAME = "supplier-hub"

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> ServiceHealth:
    return ServiceHealth(service=SERVICE_NAME, version=version(SERVICE_NAME))
