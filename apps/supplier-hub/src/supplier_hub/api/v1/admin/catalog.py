"""Every supplier's catalog, read only: the values belong to the supplier (§17.1)."""

import uuid

from fastapi import APIRouter

from service_kit.errors import NotFound
from supplier_hub.api.deps import Context, DbSession, Operator
from supplier_hub.api.v1.admin.operations import job_view
from supplier_hub.api.v1.catalog import family_detail
from supplier_hub.models import ProductFamily
from supplier_hub.models.audit import AuditAction
from supplier_hub.schemas.admin import FamilyRow, JobView
from supplier_hub.schemas.catalog import SupplierFamilyDetail
from supplier_hub.services import catalog, operations, operator_audit, supplier_catalog

router = APIRouter(prefix="/catalog")


@router.get("/families")
def list_families(
    session: DbSession, supplier: uuid.UUID | None = None, category: str | None = None
) -> list[FamilyRow]:
    return [
        FamilyRow(
            id=family.id,
            name=family.name,
            manufacturer=family.manufacturer,
            supplier=family.supplier.name,
            category_code=family.category_code,
            variants=sum(variant.is_active for variant in family.variants),
            normalized=family.normalized_hash == family.content_hash,
        )
        for family in catalog.families(session, supplier_id=supplier, category=category)
    ]


@router.get("/families/{family_id}")
def get_family(family_id: uuid.UUID, session: DbSession) -> SupplierFamilyDetail:
    family = session.get(ProductFamily, family_id)
    if family is None:
        raise NotFound("family not found")
    return family_detail(session, supplier_catalog.view_of(session, family))


@router.post("/families/{family_id}/normalize")
def renormalize_family(
    family_id: uuid.UUID, context: Context, session: DbSession, operator: Operator
) -> JobView:
    """Reads the catalog text again; the reading only fills attributes still missing."""
    job = operations.renormalize(session, family_id, now=context.clock())
    operator_audit.record(
        session,
        operator,
        AuditAction.FAMILY_RENORMALIZED,
        target_type="family",
        target_id=family_id,
        now=context.clock(),
        data={"job_id": str(job.id)},
    )
    return job_view(job)
