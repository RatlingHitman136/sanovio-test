"""Command line entry point: `demo-client <command>`."""

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
