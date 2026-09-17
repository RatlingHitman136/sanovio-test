"""Command line entry point: `demo-client <command>`."""

from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.table import Table

from demo_client.client import check_health

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
