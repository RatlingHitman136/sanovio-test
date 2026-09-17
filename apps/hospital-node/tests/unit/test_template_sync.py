from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from equivalence_core.templates import load_seed_templates
from hospital_node.core.settings import NodeSettings
from hospital_node.models.users import Role
from hospital_node.services import template_sync
from hospital_node.services.seed import SeedReport
from node_fixtures import FakeClock, article, user
from service_kit.errors import Unprocessable

PEEL_OFF_LABEL = {
    "key": "peel_off_label",
    "type": "bool",
    "labels": {"de": "Abziehetikett", "en": "Peel-off label"},
    "criticality": "major",
    "rule": "exact",
}


def _syringe_with_new_attribute() -> dict[str, object]:
    definition = load_seed_templates()["syringe_single_use"].model_dump(mode="json")
    definition["attributes"].append(PEEL_OFF_LABEL)
    return definition


def test_installing_a_definition_rebuilds_only_its_category(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    needle = article(session, "6")
    assert needle.projection is not None
    needle_before = needle.projection.updated_at
    clock.advance(hours=1)
    hub_time = datetime(2026, 9, 18, 8, 10, tzinfo=UTC)

    row = template_sync.install(
        session,
        _syringe_with_new_attribute(),
        user_id=user(session, Role.PURCHASER).id,
        settings=settings,
        now=clock(),
        hub_updated_at=hub_time,
    )

    syringe = article(session, "3")
    assert syringe.projection is not None
    assert "peel_off_label" in syringe.projection.unknown_attributes
    assert syringe.projection.definition_hash == row.definition_hash
    assert row.hub_updated_at == hub_time
    assert needle.projection.updated_at == needle_before
    assert "peel_off_label" in template_sync.installed(session)["syringe_single_use"].keys


@pytest.mark.parametrize(
    "broken",
    [
        {"code": "x"},
        {**_syringe_with_new_attribute(), "attributes": [PEEL_OFF_LABEL | {"rule": "vibes"}]},
        {**_syringe_with_new_attribute(), "attributes": [PEEL_OFF_LABEL | {"type": "number"}]},
    ],
)
def test_invalid_definitions_are_refused(
    session: Session,
    seeded: SeedReport,
    settings: NodeSettings,
    clock: FakeClock,
    broken: dict[str, object],
) -> None:
    with pytest.raises(Unprocessable, match="invalid template definition"):
        template_sync.install(
            session,
            broken,
            user_id=user(session, Role.PURCHASER).id,
            settings=settings,
            now=clock(),
        )
