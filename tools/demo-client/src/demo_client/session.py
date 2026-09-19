"""One purchaser session: a node token and a hub token held together (§19 step 0).

The hub never issues refresh tokens; when its token expires, the session asks the node for a
fresh assertion and exchanges it again, without the caller noticing.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from demo_client.hub import HubClient
from demo_client.node import NodeClient


@dataclass
class Session:
    node: NodeClient
    hub: HubClient

    def sign_in(self, email: str, password: str) -> dict[str, Any]:
        """Node login, then the assertion exchange; returns the hub's exchange response."""
        self.node.login(email, password)
        exchanged = self._exchange()
        self.hub.reauthenticate = self._exchange
        return exchanged

    def sync_templates(self) -> list[str]:
        """Installs every hub definition that is newer than the node's copy (§7.2, D52)."""
        installed = {row["code"]: row for row in self.node.templates()}
        synced = []
        for served in self.hub.templates():
            local = installed.get(served["code"])
            if local is not None and _at(local["updated_at"]) >= _at(served["updated_at"]):
                continue
            self.node.install_template(served["definition"], served["updated_at"])
            synced.append(str(served["code"]))
        return synced

    def _exchange(self) -> dict[str, Any]:
        return self.hub.exchange(self.node.assertion()["assertion"])


def _at(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp)
