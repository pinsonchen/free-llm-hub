"""Tests for admin endpoints."""

from fastapi.testclient import TestClient

from app.main import app


def test_admin_quota() -> None:
    client = TestClient(app)
    response = client.get("/admin/quota")
    assert response.status_code == 200
    body = response.json()
    assert "quotas" in body


def test_admin_compact() -> None:
    client = TestClient(app)
    response = client.post("/admin/compact")
    assert response.status_code == 200
    body = response.json()
    assert "removed_events" in body


def test_admin_reload() -> None:
    client = TestClient(app)
    response = client.post("/admin/reload")
    assert response.status_code == 200
    assert response.json()["status"] == "reloaded"
