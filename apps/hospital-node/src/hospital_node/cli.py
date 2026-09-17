"""Command line entry point: `hospital-node <command>`."""

import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from equivalence_core.exchange.keys import (
    KeyFileError,
    generate_private_key,
    jwk_thumbprint,
    public_jwk,
    write_private_key,
)
from hospital_node.core.migrations import upgrade_to_head
from hospital_node.core.settings import NodeSettings
from hospital_node.llm.factory import make_llm
from hospital_node.models.users import Role
from hospital_node.services.normalization import NormalizationUnavailable
from hospital_node.services.seed import DATASETS, SeedError
from hospital_node.services.seed import seed as seed_dataset
from hospital_node.services.user_directory import create_user as add_user
from service_kit.clock import utc_now
from service_kit.db import make_engine, make_session_factory
from service_kit.errors import Conflict
from service_kit.security import PasswordHasher

app = typer.Typer(no_args_is_help=True)

# Replaced in tests, so seeding runs against a fake LLM.
llm_factory = make_llm


@app.callback()
def main() -> None:
    """Hospital node administration."""


@app.command()
def keygen(
    out: Annotated[Path, typer.Option(help="Where to write the private key (PEM, mode 0600).")],
    kid: Annotated[str, typer.Option(help="Key id registered at the hub, e.g. ksp-2026-09.")],
) -> None:
    """Create the node's Ed25519 signing key and print the public JWK to register at the hub."""
    key = generate_private_key()
    try:
        write_private_key(key, out)
    except KeyFileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    jwk = public_jwk(key, kid)
    public_file = out.with_suffix(".pub.jwk.json")
    public_file.write_text(json.dumps(jwk, indent=2) + "\n")
    typer.echo(f"private key: {out}\npublic JWK:  {public_file}")
    typer.echo(json.dumps(jwk))
    typer.echo(f"fingerprint (confirm out of band): {jwk_thumbprint(jwk)}")


@app.command()
def migrate() -> None:
    """Bring the node database (DATABASE_URL) to the latest schema."""
    upgrade_to_head(NodeSettings().database_url)
    typer.echo("database is up to date")


@app.command()
def seed(
    dataset: Annotated[str, typer.Option(help=f"One of: {', '.join(DATASETS)}.")] = "demo_ksp",
    reset: Annotated[bool, typer.Option(help="Delete all existing data first.")] = False,
) -> None:
    """Load a demo dataset and normalize its articles (one LLM call per batch in llm mode)."""
    settings = NodeSettings()
    password = settings.node_seed_password
    if password is None or not password.get_secret_value():
        _fail("set NODE_SEED_PASSWORD (the password the demo users get) in the node's .env")
    upgrade_to_head(settings.database_url)
    engine = make_engine(settings.database_url)
    try:
        with make_session_factory(engine).begin() as session:
            report = seed_dataset(
                session,
                dataset,
                password=password.get_secret_value(),
                hasher=PasswordHasher(),
                llm=llm_factory(settings),
                settings=settings,
                now=utc_now(),
                reset=reset,
            )
    except (SeedError, NormalizationUnavailable, ValueError) as exc:
        _fail(str(exc))
    finally:
        engine.dispose()
    typer.echo(f"seeded {dataset}: {report.users} users, {report.articles} articles")


@app.command("create-user")
def create_user(
    email: Annotated[str, typer.Option()],
    display_name: Annotated[str, typer.Option()],
    role: Annotated[Role, typer.Option()] = Role.PURCHASER,
) -> None:
    """Add a node account; the password is asked for interactively."""
    password: str = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    settings = NodeSettings()
    engine = make_engine(settings.database_url)
    try:
        with make_session_factory(engine).begin() as session:
            user = add_user(
                session,
                PasswordHasher(),
                email=email,
                password=password,
                role=role,
                display_name=display_name,
            )
            typer.echo(f"created {user.email} ({user.role}), hub subject {user.hub_subject_id}")
    except (Conflict, ValueError) as exc:
        _fail(str(exc))
    finally:
        engine.dispose()


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)
