"""Command line entry point: `supplier-hub <command>`."""

import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from service_kit.clock import utc_now
from service_kit.db import make_engine, make_session_factory
from service_kit.errors import Conflict, ServiceError
from service_kit.security import PasswordHasher
from supplier_hub.core.migrations import upgrade_to_head
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.factory import make_llm
from supplier_hub.models import Organization, User
from supplier_hub.models.identity import UserRole
from supplier_hub.models.organizations import OrganizationType
from supplier_hub.services import tenants_keys
from supplier_hub.services.normalization import NormalizationUnavailable
from supplier_hub.services.seed import SeedError
from supplier_hub.services.seed import seed as seed_hub

app = typer.Typer(no_args_is_help=True)

# Replaced in tests, so seeding runs against a fake LLM.
llm_factory = make_llm


@app.callback()
def main() -> None:
    """Supplier hub administration."""


@app.command()
def migrate() -> None:
    """Bring the hub database (DATABASE_URL) to the latest schema."""
    upgrade_to_head(HubSettings().database_url)
    typer.echo("database is up to date")


@app.command()
def seed(
    reset: Annotated[bool, typer.Option(help="Delete all existing data first.")] = False,
) -> None:
    """Load the demo hub: tenants, suppliers, the registry and both catalogs."""
    settings = HubSettings()
    password = settings.hub_seed_password
    if password is None or not password.get_secret_value():
        _fail("set HUB_SEED_PASSWORD (the password the demo users get) in the hub's .env")
    upgrade_to_head(settings.database_url)
    engine = make_engine(settings.database_url)
    try:
        with make_session_factory(engine).begin() as session:
            report = seed_hub(
                session,
                password=password.get_secret_value(),
                hasher=PasswordHasher(),
                llm=llm_factory(settings),
                settings=settings,
                now=utc_now(),
                reset=reset,
            )
    except (SeedError, NormalizationUnavailable) as exc:
        _fail(str(exc))
    finally:
        engine.dispose()
    typer.echo(
        f"seeded hub: {report.tenants} tenants, {report.suppliers} suppliers, "
        f"{report.families} families, {report.variants} variants"
    )


@app.command("register-tenant")
def register_tenant(
    tenant: Annotated[str, typer.Option(help="The tenant's code, e.g. ten_ksp.")],
    jwk_file: Annotated[Path, typer.Option(help="The node's public JWK from `make keys`.")],
) -> None:
    """Register a node's public signing key; confirm the fingerprint out of band (§17)."""
    settings = HubSettings()
    engine = make_engine(settings.database_url)
    try:
        with make_session_factory(engine).begin() as session:
            operator = _operator(session).id
            tenants = {org.code: org for org in tenants_keys.tenants(session)}
            if tenant not in tenants:
                _fail(f"no tenant {tenant!r}; seed the hub first")
            key = tenants_keys.register_key(
                session,
                tenants[tenant],
                public_jwk=json.loads(jwk_file.read_text()),
                not_before=utc_now(),
                registered_by=operator,
            )
            typer.echo(f"registered {key.kid} for {tenant}")
            typer.echo(f"fingerprint (confirm out of band): {key.fingerprint}")
    except ServiceError as exc:
        if isinstance(exc, Conflict) and exc.code == "KID_TAKEN":
            typer.echo(f"{exc}; nothing to do")
            return
        _fail(str(exc))
    finally:
        engine.dispose()


@app.command("create-operator")
def create_operator(
    email: Annotated[str, typer.Option()],
    display_name: Annotated[str, typer.Option()],
) -> None:
    """Add an operator account; the password is asked for interactively."""
    password: str = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    settings = HubSettings()
    engine = make_engine(settings.database_url)
    try:
        with make_session_factory(engine).begin() as session:
            org = session.scalar(
                select(Organization).where(Organization.type == OrganizationType.OPERATOR)
            )
            if org is None:
                _fail("no operator organization; seed the hub first")
            user = User(
                org_id=org.id,
                email=email.lower(),
                password_hash=PasswordHasher().hash(password),
                role=UserRole.OPERATOR,
                display_name=display_name,
            )
            session.add(user)
            typer.echo(f"created {user.email} (OPERATOR)")
    finally:
        engine.dispose()


def _operator(session: Session) -> User:
    """Key registration is an operator action, so it is recorded against one (H.2)."""
    operator = session.scalar(select(User).where(User.role == UserRole.OPERATOR))
    if operator is None:
        _fail("no operator account; seed the hub first")
    return operator


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)
