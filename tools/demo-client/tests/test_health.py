import httpx

from demo_client.client import check_health


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_healthy_service_is_reported_up() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"status": "ok", "service": "hospital-node", "version": "0.1.0"}
        )
    )

    status = check_health(_client(transport), "hospital node", "http://node")

    assert status.up
    assert status.detail == "hospital-node 0.1.0"


def test_unreachable_service_is_reported_down() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    status = check_health(_client(httpx.MockTransport(refuse)), "supplier hub", "http://hub")

    assert not status.up
    assert "connection refused" in status.detail


def test_unexpected_response_is_reported_down() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"status": "bad"}))

    status = check_health(_client(transport), "supplier hub", "http://hub")

    assert not status.up
