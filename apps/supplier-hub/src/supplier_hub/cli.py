"""Command line entry point: `supplier-hub <command>`."""

import contextlib
import json
import tempfile
import threading
from dataclasses import asdict
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
from supplier_hub.evals import answers, verdicts
from supplier_hub.jobs import handlers
from supplier_hub.jobs.worker import Worker
from supplier_hub.llm.extract_answer import PROMPT_VERSION as EXTRACT_PROMPT
from supplier_hub.llm.factory import make_llm
from supplier_hub.llm.fakes import fake_llm
from supplier_hub.llm.judge import PROMPT_VERSION as JUDGE_PROMPT
from supplier_hub.models import Organization, User
from supplier_hub.models.identity import UserRole
from supplier_hub.models.organizations import OrganizationType
from supplier_hub.services import assessment, tenants_keys
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


@app.command()
def worker() -> None:
    """Run the job queue on its own, next to API processes started with WORKER_ENABLED=false."""
    settings = HubSettings()
    upgrade_to_head(settings.database_url)
    engine = make_engine(settings.database_url)
    running = Worker(
        make_session_factory(engine),
        handlers.build(llm=llm_factory(settings), settings=settings),
        clock=utc_now,
        on_give_up=assessment.give_up,
    )
    running.start()
    typer.echo("worker running; Ctrl+C stops it")
    try:
        _wait_until_interrupted()
    finally:
        running.stop()
        engine.dispose()
    typer.echo("worker stopped")


def _wait_until_interrupted() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        threading.Event().wait()


@app.command("eval")
def run_eval(
    fake: Annotated[
        bool, typer.Option(help="Run the harness offline with the scripted fake LLM.")
    ] = False,
    out: Annotated[Path, typer.Option(help="Where the result file goes.")] = Path("var/evals"),
) -> None:
    """Score round-1 verdicts, critical-gap questions, judge calls and answer extraction (§9)."""
    settings = HubSettings()
    if not fake and settings.llm_mode != "anthropic":
        _fail("set LLM_MODE=anthropic and ANTHROPIC_API_KEY in the hub's .env, or pass --fake")
    llm = fake_llm() if fake else llm_factory(settings)
    if llm is None:
        _fail("no LLM client: set ANTHROPIC_API_KEY in the hub's .env")
    now = utc_now()
    with tempfile.TemporaryDirectory() as workdir:
        scored = verdicts.run(llm=llm, settings=settings, workdir=Path(workdir), now=now)
    extracted = answers.run(llm=llm, settings=settings)
    report = {
        "service": "supplier-hub",
        "created_at": now.isoformat(),
        "llm": "fake" if fake else "anthropic",
        "models": {"judge": settings.judge_model, "extract_answer": settings.extract_answer_model},
        "prompt_versions": {"judge": JUDGE_PROMPT, "extract_answer": EXTRACT_PROMPT},
        "targets": {"verdict": verdicts.VERDICT_TARGET, "critical_gaps": verdicts.GAP_TARGET},
        "verdict_accuracy": round(scored.verdict_accuracy, 4),
        "critical_gap_recall": round(scored.gap_recall, 4),
        "judge_accuracy": scored.judge_accuracy,
        "extract_accuracy": round(extracted.accuracy, 4),
        "passed": scored.passed,
        "cases": [asdict(case) for case in scored.cases],
        "answers": [asdict(answer) for answer in extracted.answers],
        "usage": [asdict(u) for u in scored.usage + extracted.usage],
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{now:%Y%m%d-%H%M%S}-hub.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    wrong = {c.id: f"{c.verdict} ≠ {c.expected_verdict}" for c in scored.cases if not c.verdict_ok}
    typer.echo(f"verdicts: {scored.verdict_accuracy:.0%} (target 85%) {wrong or ''}")
    typer.echo(f"critical gaps asked: {scored.gap_recall:.0%} (target 100%)")
    if scored.judge_accuracy is not None:
        typer.echo(f"judge on semantic attributes: {scored.judge_accuracy:.0%}")
    misread = [a.comment for a in extracted.answers if not a.ok]
    typer.echo(f"answer extraction: {extracted.accuracy:.0%} {misread or ''}")
    for u in scored.usage + extracted.usage:
        typer.echo(f"  {u.model}: {u.calls} calls, ${u.cost_usd:.4f}, {u.mean_latency_ms} ms")
    typer.echo(f"written to {path}")
    if not scored.passed:
        raise typer.Exit(code=1)


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
