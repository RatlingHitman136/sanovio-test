"""Operator administration (§17.1). Every route sits behind the operator guard, so a route
added later cannot forget it; each change is written to the audit trail (H.23)."""

from fastapi import APIRouter, Depends

from supplier_hub.api.deps import operator_only
from supplier_hub.api.v1.admin import (
    accounts,
    audit,
    catalog,
    curation,
    operations,
    templates,
    tenants,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(operator_only)])
for module in (tenants, curation, templates, accounts, catalog, operations, audit):
    router.include_router(module.router)
