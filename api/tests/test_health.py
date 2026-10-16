"""Contract test 1: /health is open and reports status + version."""

import pytest

pytestmark = [pytest.mark.foundations, pytest.mark.smoke]


def test_health_needs_no_auth(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
