"""Command line entry point: `demo-client <command>`."""

import json
from typing import Annotated, Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from demo_client.client import check_health
from demo_client.hub import HubClient
from demo_client.node import NodeClient

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Drives the hospital node and the supplier hub the way the purchaser app will."""


@app.command()
def health(
    node_url: Annotated[
        str, typer.Option(help="Hospital node base URL.")
    ] = "http://127.0.0.1:8001",
    hub_url: Annotated[str, typer.Option(help="Supplier hub base URL.")] = "http://127.0.0.1:8000",
) -> None:
    """Check that both services are up; exits with 1 if either is not."""
    with httpx.Client(timeout=5.0) as http:
        statuses = [
            check_health(http, "hospital node", node_url),
            check_health(http, "supplier hub", hub_url),
        ]
    table = Table("service", "url", "status", "detail")
    for status in statuses:
        state = "[green]up[/green]" if status.up else "[red]down[/red]"
        table.add_row(status.name, status.base_url, state, status.detail)
    Console().print(table)
    if not all(status.up for status in statuses):
        raise typer.Exit(code=1)


@app.command("node-demo")
def node_demo(
    node_url: Annotated[
        str, typer.Option(help="Hospital node base URL.")
    ] = "http://127.0.0.1:8001",
    email: Annotated[str, typer.Option(help="Purchaser account.")] = "anna.meier@demo-ksp.example",
    password: Annotated[
        str, typer.Option(envvar="NODE_SEED_PASSWORD", help="Password of the demo accounts.")
    ] = "",
    admin_email: Annotated[
        str, typer.Option(help="Node admin, who may read the egress log.")
    ] = "it-admin@demo-ksp.example",
) -> None:
    """Walk through the standalone node: articles, a requirement, an assertion, the egress log."""
    console = Console()
    if not password:
        console.print("[red]set NODE_SEED_PASSWORD (the password `make seed` used)[/red]")
        raise typer.Exit(code=1)
    with httpx.Client(timeout=30.0) as http:
        node = NodeClient(http, node_url)
        node.login(email, password)
        console.print(f"logged in as [bold]{node.me()['display_name']}[/bold]")

        articles = node.articles()
        table = Table("id", "article", "category", "source", "data quality")
        for article in articles:
            table.add_row(
                article["internal_id"],
                article["name"],
                article["category_code"],
                article["category_source"],
                ", ".join(article["data_quality_issues"]) or "-",
            )
        console.print(table)

        for internal_id in ("3", "6"):
            summary = next(a for a in articles if a["internal_id"] == internal_id)
            detail = node.article(summary["id"])
            facts = Table("attribute", "value", "source", "quote", title=detail["name"])
            for attribute in detail["attributes"]:
                facts.add_row(
                    attribute["key"],
                    str(attribute["value"].get("value")),
                    attribute["source"],
                    attribute["quote"] or "-",
                )
            console.print(facts)
            console.print(f"unknown: {', '.join(detail['unknown_attributes']) or '-'}")

        syringe = next(a for a in articles if a["internal_id"] == "3")
        issued = node.requirement(syringe["id"])
        console.print("\n[bold]what would leave the hospital[/bold]")
        console.print_json(data=issued["requirement"])

        assertion = node.assertion()
        console.print(f"hub assertion valid until {assertion['expires_at']}")

        console.print("\n[bold]requirements until the node refuses[/bold]")
        attempts = 1
        while node.requirement_status(syringe["id"]) != 429:
            attempts += 1
            if attempts > 500:  # the configured limit is far below this
                console.print("[red]no rate limit hit; check REQUIREMENT_RATE_LIMIT_PER_HOUR[/red]")
                raise typer.Exit(code=1)
        console.print(f"429 after {attempts} requirements in this hour")

        admin = NodeClient(http, node_url)
        admin.login(admin_email, password)
        log = admin.egress()
        egress = Table("time", "kind", "user", "sha-256", "alert")
        for entry in log["entries"][:10]:
            egress.add_row(
                entry["created_at"],
                entry["kind"],
                entry["user"],
                (entry["content_sha256"] or "-")[:12],
                entry["alert"] or "-",
            )
        console.print(egress)
        console.print(f"issued per user: {log['issued_per_user']}, alerts: {log['alerts']}")


@app.command("demo-search")
def demo_search(
    node_url: Annotated[
        str, typer.Option(help="Hospital node base URL.")
    ] = "http://127.0.0.1:8001",
    hub_url: Annotated[str, typer.Option(help="Supplier hub base URL.")] = "http://127.0.0.1:8000",
    email: Annotated[str, typer.Option(help="Purchaser account.")] = "anna.meier@demo-ksp.example",
    password: Annotated[
        str, typer.Option(envvar="NODE_SEED_PASSWORD", help="Password of the demo accounts.")
    ] = "",
    internal_id: Annotated[str, typer.Option(help="Which article to search with.")] = "3",
) -> None:
    """Both sides at once: build a requirement at the node, exchange, search at the hub."""
    console = Console()
    if not password:
        console.print("[red]set NODE_SEED_PASSWORD (the password `make seed` used)[/red]")
        raise typer.Exit(code=1)
    with httpx.Client(timeout=30.0) as http:
        node = NodeClient(http, node_url)
        node.login(email, password)
        article = next(a for a in node.articles() if a["internal_id"] == internal_id)
        issued = node.requirement(article["id"])
        requirement = issued["requirement"]
        console.print(
            f"[bold]{article['name']}[/bold] → requirement for {requirement['template_code']} "
            f"({len(requirement['attributes'])} attributes, "
            f"{len(requirement['unknown_attributes'])} unknown)"
        )

        hub = HubClient(http, hub_url)
        exchanged = hub.exchange(node.assertion()["assertion"])
        console.print(f"exchanged at the hub as [bold]{exchanged['tenant_alias']}[/bold]")

        result = hub.search(requirement)
        _print_candidates(console, result)

        excluded = result["excluded_by"]
        console.print(
            f"excluded by a known contradiction: {excluded or 'nothing'} · "
            f"hospital gaps: {len(result['hospital_gaps'])}"
        )


# What the purchaser knows about art_03 that its master data does not say (§21, scenario 1).
PURCHASER_ANSWERS: dict[str, dict[str, Any]] = {
    "single_use": {"type": "bool", "value": True},
    "standards": {"type": "list", "value": ["ISO 7886-1"]},
    "special_scale": {"type": "text", "value": "keine"},
    "needle_included": {"type": "bool", "value": False},
    "safety_mechanism": {"type": "bool", "value": False},
    "pump_compatible": {"type": "bool", "value": False},
    "light_protected": {"type": "bool", "value": False},
}


@app.command("demo-assessment")
def demo_assessment(
    node_url: Annotated[
        str, typer.Option(help="Hospital node base URL.")
    ] = "http://127.0.0.1:8001",
    hub_url: Annotated[str, typer.Option(help="Supplier hub base URL.")] = "http://127.0.0.1:8000",
    email: Annotated[str, typer.Option(help="Purchaser account.")] = "anna.meier@demo-ksp.example",
    password: Annotated[
        str, typer.Option(envvar="NODE_SEED_PASSWORD", help="Password of the node demo accounts.")
    ] = "",
    admin_email: Annotated[
        str, typer.Option(help="Node admin, who may read the egress log.")
    ] = "it-admin@demo-ksp.example",
    operator_email: Annotated[
        str, typer.Option(help="Hub operator, who may run the supplier simulator.")
    ] = "ops@sanovio-demo.example",
    hub_password: Annotated[
        str, typer.Option(envvar="HUB_SEED_PASSWORD", help="Password of the hub demo accounts.")
    ] = "",
) -> None:
    """Scenario 1 over HTTP only: search, current product, assessment, questions, simulated
    supplier answers, round 2 and the resolution; then what left the hospital."""
    console = Console()
    if not password or not hub_password:
        console.print(
            "[red]set NODE_SEED_PASSWORD and HUB_SEED_PASSWORD (as for `make seed`)[/red]"
        )
        raise typer.Exit(code=1)
    with httpx.Client(timeout=30.0) as http:
        node = NodeClient(http, node_url)
        node.login(email, password)
        article = next(a for a in node.articles() if a["internal_id"] == "3")
        hub = HubClient(http, hub_url)
        hub.exchange(node.assertion()["assertion"])
        issued: list[dict[str, Any]] = []

        def issue(answered: tuple[str, ...] = ()) -> dict[str, Any]:
            requirement: dict[str, Any] = node.requirement(article["id"], answered)["requirement"]
            issued.append(requirement)
            return requirement

        console.print(f"[bold]1. search[/bold] with {article['name']}")
        found = hub.search(issue(), limit=50)["candidates"]
        by_article = {candidate["article_no"]: candidate for candidate in found}
        injekt, plastipak = by_article["4606728V"], by_article["300912"]

        console.print(f"[bold]2. current product[/bold]: {injekt['display_name']}")
        node.set_reference(article["id"], hub.variant_attributes(injekt["variant_id"]))

        console.print(f"[bold]3. assessment[/bold] against {plastipak['display_name']}")
        opened = hub.open_assessment(issue(), plastipak["variant_id"])
        detail = hub.settled(opened["id"])
        _print_round(console, detail)

        console.print("[bold]4. questions[/bold]")
        answered: list[str] = []
        for question in _drafts(detail, "PURCHASER"):
            key = question["attribute_key"]
            if key in PURCHASER_ANSWERS:
                node.set_fact(article["id"], key, PURCHASER_ANSWERS[key], question["id"])
                answered.append(question["id"])
                console.print(f"  purchaser answers {key} at the node")
            else:
                hub.withdraw_question(detail["id"], question["id"], detail["version"])
                console.print(f"  purchaser withdraws {key}")
            detail = hub.assessment(detail["id"])
        if answered:
            hub.add_requirement(detail["id"], issue(tuple(answered)), detail["version"])
            detail = hub.assessment(detail["id"])
        # With nothing left for the supplier, the purchaser's answers alone start the next round.
        if detail["status"] == "NEEDS_QUESTION_REVIEW":
            for question in _drafts(detail, "SUPPLIER"):
                console.print(f"  to the supplier: {question['text']}")
            status = hub.send_questions(detail["id"], detail["version"])["status"]
            console.print(f"  sent → {status}")
            if status == "AWAITING_ANSWERS":
                console.print("[bold]5. the supplier answers[/bold] (development simulator)")
                operator = HubClient(http, hub_url)
                operator.login(operator_email, hub_password)
                operator.simulate_supplier(detail["id"])
        detail = hub.settled(detail["id"])
        _print_round(console, detail)

        if detail["status"] == "PROPOSED_RESOLUTION":
            detail = hub.resolve(detail["id"], detail["proposed_verdict"], detail["version"])
        console.print(f"[bold]6. result[/bold]: {detail['status']} · {detail['final_verdict']}")

        _print_leak_check(console, node.article(article["id"]), issued)
        admin = NodeClient(http, node_url)
        admin.login(admin_email, password)
        log = admin.egress()
        console.print(f"egress log: {len(log['entries'])} entries, alerts: {log['alerts']}")


def _drafts(detail: dict[str, Any], addressee: str) -> list[dict[str, Any]]:
    return [
        q for q in detail["questions"] if q["addressee"] == addressee and q["status"] == "DRAFT"
    ]


def _print_round(console: Console, detail: dict[str, Any]) -> None:
    last = detail["rounds"][-1]
    console.print(
        f"  round {last['round_no']}: rules {last['rule_verdict']}, judge "
        f"{last['llm_verdict'] or '-'} → {detail['status']}"
    )
    if last["rationale"]:
        console.print(f"  [dim]{last['rationale']}[/dim]")


def _print_leak_check(
    console: Console, article: dict[str, Any], issued: list[dict[str, Any]]
) -> None:
    """Every requirement that left, searched for what must never leave (§16)."""
    secrets = [article["name"], article["brand"], article["target_net_price"]]
    secrets += [identifier["value"] for identifier in article["identifiers"]]
    wire = json.dumps(issued, ensure_ascii=False)
    leaked = [secret for secret in secrets if secret and secret in wire]
    if leaked:
        console.print(f"[red]left the hospital: {leaked}[/red]")
        raise typer.Exit(code=1)
    console.print(
        f"{len(issued)} requirements left the hospital; none contains the name, brand, "
        "price or an identifier"
    )


def _print_candidates(console: Console, result: dict[str, Any]) -> None:
    table = Table(
        "article", "candidate", "supplier", "score", "coverage", "critical unknowns", "id match"
    )
    for candidate in result["candidates"][:10]:
        table.add_row(
            candidate["article_no"],
            candidate["display_name"],
            candidate["supplier"],
            f"{candidate['score']:.2f}",
            f"{candidate['coverage']:.0%}",
            str(candidate["critical_unknowns"]),
            candidate["identifier_match"] or "-",
        )
    console.print(table)
    console.print(f"hard filters: {', '.join(result['search_spec']['hard_filters']) or '-'}")
