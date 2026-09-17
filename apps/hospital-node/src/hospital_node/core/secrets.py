"""Secrets the node loads once at startup and keeps in memory only."""

from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from equivalence_core.exchange.keys import load_private_key
from hospital_node.core.settings import NodeSettings


@dataclass(frozen=True)
class NodeSecrets:
    signing_key: Ed25519PrivateKey
    signing_kid: str

    def __repr__(self) -> str:
        # Keep the key out of logs and tracebacks.
        return f"NodeSecrets(signing_kid={self.signing_kid!r})"


def load_node_secrets(settings: NodeSettings) -> NodeSecrets:
    return NodeSecrets(
        signing_key=load_private_key(settings.node_signing_key_file),
        signing_kid=settings.node_signing_kid,
    )
