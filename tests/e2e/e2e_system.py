"""The in-process system the e2e tests drive: both apps, their clients and the actors."""

from dataclasses import dataclass

from fastapi.testclient import TestClient
from rich.console import Console

from demo_client.hub import HubClient
from demo_client.node import NodeClient
from demo_client.scenarios.common import Actors
from demo_client.session import Session
from hospital_node.core.settings import NodeSettings
from hub_fixtures import PASSWORD, FakeClock, node_key
from supplier_hub.api.deps import HubContext

BASE_URL = "http://testserver"
PURCHASER = "anna.meier@demo-ksp.example"
NODE_ADMIN = "it-admin@demo-ksp.example"
OPERATOR = "ops@sanovio-demo.example"


@dataclass
class System:
    node_settings: NodeSettings
    clock: FakeClock
    node: TestClient
    hub: TestClient

    def hub_context(self) -> HubContext:
        context: HubContext = self.hub.app.state.hub  # type: ignore[attr-defined]
        return context

    def purchaser(self, node: TestClient | None = None) -> Session:
        """Anna's session; `node` swaps in another app on the same node database."""
        session = Session(NodeClient(node or self.node, BASE_URL), self.hub_client())
        session.sign_in(PURCHASER, PASSWORD)
        return session

    def hub_client(self) -> HubClient:
        client = HubClient(self.hub, BASE_URL)
        client.sleep = lambda _: self.hub_context().run_jobs()
        return client

    def operator(self) -> HubClient:
        client = self.hub_client()
        client.login(OPERATOR, PASSWORD)
        return client

    def node_admin(self) -> NodeClient:
        client = NodeClient(self.node, BASE_URL)
        client.login(NODE_ADMIN, PASSWORD)
        return client

    def second_hospital(self) -> HubClient:
        """A purchaser of ten_spital2, which exists only at the hub (D55): the test holds its
        node key and signs the assertion itself."""
        key = node_key(tenant_code="ten_spital2", kid="sp2-e2e")
        operator = self.operator()
        tenant = next(t for t in operator.tenants() if t["code"] == "ten_spital2")
        operator.register_key(tenant["id"], key.jwk())
        hub = HubClient(self.hub, BASE_URL)
        hub.exchange(key.assertion(self.clock(), subject="sub_2B7Q9M3X5K8T1Z4W6N0R"))
        return hub

    def actors(self) -> Actors:
        return Actors(self.purchaser(), self.operator(), self.node_admin(), Console(quiet=True))


def register_node_key(system: System, tenant_code: str = "ten_ksp") -> None:
    """Onboarding as the runbook has it: the node shows its public key, an operator
    registers it for the tenant (§17)."""
    public = system.node_admin().signing_key()
    operator = system.operator()
    tenant = next(t for t in operator.tenants() if t["code"] == tenant_code)
    operator.register_key(tenant["id"], public["public_jwk"])
