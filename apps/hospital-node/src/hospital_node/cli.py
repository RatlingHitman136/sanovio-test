"""Command line entry point: `hospital-node <command>`."""

import json
from pathlib import Path
from typing import Annotated

import typer

from equivalence_core.exchange.keys import (
    KeyFileError,
    generate_private_key,
    jwk_thumbprint,
    public_jwk,
    write_private_key,
)

app = typer.Typer(no_args_is_help=True)


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
