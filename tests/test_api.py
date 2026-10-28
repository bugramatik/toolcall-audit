"""Tests for the FastAPI routes, backed by an in-memory SQLite engine."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from toolcall_audit.api import app, get_engine
from toolcall_audit.store import init_db, make_engine

ROOT = Path(__file__).resolve().parents[1]
SESSION_PATH = ROOT / "data" / "session-example.json"
POLICY_PATH = ROOT / "policy" / "default.yaml"


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    engine = make_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    init_db(engine)
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_replay_returns_report(client: TestClient) -> None:
    payload = {"session_path": str(SESSION_PATH), "policy_path": str(POLICY_PATH)}
    response = client.post("/replay", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "sess-2025-03-04-a"
    assert body["total"] == 12
    assert len(body["verdicts"]) == 12


def test_report_roundtrip(client: TestClient) -> None:
    payload = {"session_path": str(SESSION_PATH), "policy_path": str(POLICY_PATH)}
    created = client.post("/replay", json=payload).json()
    response = client.get(f"/reports/{created['session_id']}")
    assert response.status_code == 200
    stored = response.json()
    assert stored["denied"] == created["denied"]
    assert stored["drift"] == created["drift"]


def test_unknown_report_404(client: TestClient) -> None:
    response = client.get("/reports/sess-does-not-exist")
    assert response.status_code == 404
