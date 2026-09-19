"""Command line entry point: `hospital-node <command>`."""

import json
import tempfile
from dataclasses import asdict
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
from hospital_node.evals import extraction
from hospital_node.llm.factory import make_llm
from hospital_node.llm.normalize_article import PROMPT_VERSION
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


@app.command("eval")
def run_eval(
    mode: Annotated[
        str, typer.Option(help="rules, llm (needs the hospital's key) or both.")
    ] = "both",
    out: Annotated[Path, typer.Option(help="Where the result file goes.")] = Path("var/evals"),
) -> None:
    """Score normalization of the 10 demo names against the golden set (§9, target ≥90%)."""
    if mode not in ("rules", "llm", "both"):
        _fail("--mode must be rules, llm or both")
    settings = NodeSettings()
    modes: list[extraction.Mode] = ["rules", "llm"] if mode == "both" else [mode]  # type: ignore[list-item]
    llm = llm_factory(settings.model_copy(update={"normalize_mode": "llm"}))
    if "llm" in modes and llm is None:
        _fail("the llm mode needs ANTHROPIC_API_KEY in the node's .env (or run --mode rules)")
    now = utc_now()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as workdir:
        results = [
            extraction.run(
                m,
                llm=llm if m == "llm" else None,
                settings=settings,
                workdir=Path(workdir),
                now=now,
            )
            for m in modes
        ]
    report = {
        "service": "hospital-node",
        "created_at": now.isoformat(),
        "model": settings.normalize_model,
        "prompt_version": PROMPT_VERSION,
        "target": extraction.TARGET,
        "runs": [
            {
                "mode": r.mode,
                "accuracy": round(r.accuracy, 4),
                "passed": r.passed,
                "extras": r.extras,
                "articles": [asdict(a) for a in r.articles],
                "usage": [asdict(u) for u in r.usage],
            }
            for r in results
        ],
    }
    path = out / f"{now:%Y%m%d-%H%M%S}-node-extraction.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for r in results:
        misses = {a.internal_id: a.missed for a in r.articles if a.missed or not a.category_ok}
        typer.echo(f"{r.mode}: {r.accuracy:.0%} (target {extraction.TARGET:.0%}), misses {misses}")
        for u in r.usage:
            typer.echo(f"  {u.model}: {u.calls} calls, ${u.cost_usd:.4f}, {u.mean_latency_ms} ms")
    typer.echo(f"written to {path}")
    if not all(r.passed for r in results):
        raise typer.Exit(code=1)


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)
