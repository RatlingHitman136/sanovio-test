"""What every scenario shares: the actors, named checks and the steps of the loop (§19, §21).

A scenario only drives the public APIs, exactly as the purchaser app will; it follows the
hub's actual state instead of assuming one, so it runs the same against fake and real models.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.table import Table

from demo_client.api import ApiError
from demo_client.hub import HubClient
from demo_client.node import NodeClient
from demo_client.session import Session

# A PURCHASER question the scripted purchaser cannot answer is withdrawn.
type Knowledge = Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ScenarioResult:
    title: str
    checks: list[Check] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: object = "") -> bool:
        self.checks.append(Check(name, ok, str(detail)))
        return ok

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


@dataclass
class Actors:
    """The purchaser's session, a hub operator (runs the dev simulator) and a node admin
    (reads the egress log)."""

    purchaser: Session
    operator: HubClient
    node_admin: NodeClient
    console: Console


@dataclass
class Purchase:
    """One of the hospital's articles on its way through search and assessment."""

    actors: Actors
    article: dict[str, Any]
    issued: int = 0

    @classmethod
    def of(cls, actors: Actors, internal_id: str) -> Purchase:
        node = actors.purchaser.node
        summary = next(a for a in node.articles() if a["internal_id"] == internal_id)
        return cls(actors, node.article(summary["id"]))

    def requirement(self, answered: Sequence[str] = ()) -> dict[str, Any]:
        self.issued += 1
        issued: dict[str, Any] = self.actors.purchaser.node.requirement(
            self.article["id"], answered
        )["requirement"]
        return issued

    def search(self) -> dict[str, Any]:
        return self.actors.purchaser.hub.search(self.requirement(), limit=50)

    def refresh(self) -> None:
        self.article = self.actors.purchaser.node.article(self.article["id"])


def open_assessment(purchase: Purchase, variant_id: str) -> Any:
    """Opens the assessment and waits for round 1. A pair left open by an earlier demo run
    is cancelled first, so a scenario can be repeated on the same databases."""
    hub = purchase.actors.purchaser.hub
    try:
        opened = hub.open_assessment(purchase.requirement(), variant_id)
    except ApiError as refused:
        if refused.status != 409 or "ASSESSMENT_OPEN" not in refused.body:
            raise
        earlier = str(json.loads(refused.body)["assessment_id"])
        hub.cancel(earlier, hub.assessment(earlier)["version"])
        purchase.actors.console.print("  (an earlier run left this pair open; cancelled it)")
        opened = hub.open_assessment(purchase.requirement(), variant_id)
    return hub.settled(opened["id"])


def drive(
    purchase: Purchase,
    detail: dict[str, Any],
    knowledge: Knowledge,
    *,
    in_review: Callable[[dict[str, Any]], None] | None = None,
    max_rounds: int = 4,
) -> Any:
    """Runs review rounds until the hub stops asking. `in_review` acts once, in the first
    review, before anything is answered or sent (e.g. the purchaser adds a question)."""
    hub, console = purchase.actors.purchaser.hub, purchase.actors.console
    while detail["status"] == "NEEDS_QUESTION_REVIEW" and len(detail["rounds"]) <= max_rounds:
        if in_review is not None:
            in_review(detail)
            in_review = None
            detail = hub.assessment(detail["id"])
        detail = answer_purchaser(purchase, detail, knowledge)
        detail = send_and_answer(purchase.actors, detail)
        print_round(console, detail)
    return detail


def candidate(result: Mapping[str, Any], article_no: str) -> dict[str, Any] | None:
    found: dict[str, Any] | None = next(
        (c for c in result["candidates"] if c["article_no"] == article_no), None
    )
    return found


def answer_purchaser(purchase: Purchase, detail: dict[str, Any], knowledge: Knowledge) -> Any:
    """Answers at the node what the purchaser knows, withdraws the rest, and forwards the
    node's new requirement (§11, purchaser-addressed questions)."""
    hub, node = purchase.actors.purchaser.hub, purchase.actors.purchaser.node
    console = purchase.actors.console
    answered = []
    for question in drafts(detail, "PURCHASER"):
        key = question["attribute_key"]
        if key in knowledge:
            node.set_fact(purchase.article["id"], key, knowledge[key], question["id"])
            answered.append(question["id"])
            console.print(f"  purchaser answers {key} at the node")
        else:
            hub.withdraw_question(detail["id"], question["id"], detail["version"])
            console.print(f"  purchaser withdraws {key}")
        detail = hub.assessment(detail["id"])
    if answered:
        hub.add_requirement(detail["id"], purchase.requirement(answered), detail["version"])
        detail = hub.assessment(detail["id"])
    return detail


def send_and_answer(actors: Actors, detail: dict[str, Any]) -> Any:
    """Sends the review's questions; BD or B. Braun answers through the dev simulator.
    Nothing to send means the purchaser's answers alone start the next round."""
    hub, console = actors.purchaser.hub, actors.console
    if detail["status"] == "NEEDS_QUESTION_REVIEW":
        for question in drafts(detail, "SUPPLIER"):
            console.print(f"  to the supplier: {question['text']}")
        status = _send(hub, detail["id"])
        console.print(f"  sent → {status}")
        if status == "AWAITING_ANSWERS":
            console.print("  the supplier answers (development simulator)")
            actors.operator.simulate_supplier(detail["id"])
    return hub.settled(detail["id"])


def _send(hub: HubClient, assessment_id: str, attempts: int = 60) -> str:
    """Retries while attribute proposals are still running (409, §7.2 step 2)."""
    for _ in range(attempts):
        version = hub.assessment(assessment_id)["version"]
        try:
            return str(hub.send_questions(assessment_id, version)["status"])
        except ApiError as refused:
            if refused.status != 409 or "ATTRIBUTE_PROPOSAL_PENDING" not in refused.body:
                raise
        hub.sleep(0.5)
    raise ApiError("POST", "send-questions", 409, "attribute proposals never finished")


def drafts(detail: Mapping[str, Any], addressee: str) -> list[dict[str, Any]]:
    return [
        q for q in detail["questions"] if q["addressee"] == addressee and q["status"] == "DRAFT"
    ]


def print_round(console: Console, detail: Mapping[str, Any]) -> None:
    last = detail["rounds"][-1]
    console.print(
        f"  round {last['round_no']}: rules {last['rule_verdict']}, judge "
        f"{last['llm_verdict'] or '-'} → {detail['status']}"
    )
    table = Table("attribute", "status", "hospital", "supplier", "decided by")
    for judgment in last["attribute_judgments"]:
        table.add_row(
            judgment["attribute_key"],
            judgment["status"],
            _value(judgment.get("hospital")),
            _value(judgment.get("supplier")),
            judgment.get("decided_by") or "-",
        )
    console.print(table)
    if last["rationale"]:
        console.print(f"  [dim]{last['rationale']}[/dim]")


def _value(side: Mapping[str, Any] | None) -> str:
    if not side or side.get("value") is None:
        return "-"
    value = side["value"]
    return str(value.get("value") if isinstance(value, Mapping) else value)


def egress_ids(actors: Actors) -> set[str]:
    return {entry["id"] for entry in actors.node_admin.egress()["entries"]}


def new_egress(actors: Actors, before: set[str]) -> list[dict[str, Any]]:
    return [e for e in actors.node_admin.egress()["entries"] if e["id"] not in before]


def leaked(article: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> list[str]:
    """Searches what actually left the node (the egress log's content) for what must never
    leave: the article's name, brand, price and identifier values (§16)."""
    secrets = [article["name"], article["brand"], article["target_net_price"]]
    secrets += [identifier["value"] for identifier in article["identifiers"]]
    wire = json.dumps([entry["content"] for entry in entries], ensure_ascii=False)
    return [secret for secret in secrets if secret and secret in wire]
