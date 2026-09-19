"""The §21 demo scenarios, runnable against live services or in-process apps alike."""

from collections.abc import Callable

from demo_client.scenarios import s1_full_loop, s2_early_stop, s3_manual_decision, s4_identifiers
from demo_client.scenarios.common import Actors, ScenarioResult

SCENARIOS: dict[int, Callable[[Actors], ScenarioResult]] = {
    1: s1_full_loop.run,
    2: s2_early_stop.run,
    3: s3_manual_decision.run,
    4: s4_identifiers.run,
}
