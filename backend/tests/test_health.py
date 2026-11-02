from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_does_not_touch_dependencies(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_each_dependency_individually(client: TestClient) -> None:
    """A missing database must be reported, not raised as a 500.

    This is the graceful-degradation requirement from PRD section 19: the
    dashboard needs to show which backing service is down.
    """
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    names = {component["name"] for component in body["components"]}
    assert {"database", "redis", "worker"} <= names
    assert body["status"] in {"ok", "degraded"}


def test_readiness_is_not_ok_when_a_component_is_down(client: TestClient) -> None:
    body = client.get("/health/ready").json()
    down = [c for c in body["components"] if not c["ok"]]
    if down:
        assert body["status"] == "degraded"
        assert all(component["detail"] for component in down)


def test_every_response_carries_a_correlation_id(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.headers.get("X-Correlation-ID")


def test_inbound_correlation_id_is_echoed_back(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Correlation-ID": "trace-abc-123"})
    assert response.headers["X-Correlation-ID"] == "trace-abc-123"


def test_runtime_info_advertises_capabilities_honestly(client: TestClient) -> None:
    body = client.get("/api/v1/info").json()
    assert body["api_version"] == "v1"
    assert body["execution_model"] == "local_first"
    # AI is not wired yet; claiming otherwise would let the UI imply a feature.
    assert body["ai_enabled"] is False


def test_unknown_route_uses_the_standard_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
