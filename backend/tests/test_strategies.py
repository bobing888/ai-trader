"""Tests for strategies CRUD + GitHub sync endpoints"""

import json

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal, init_db
from app.db.models import Strategy
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    init_db()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def test_list_strategies_empty(client):
    r = client.get("/api/strategies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_strategy(client):
    payload = {
        "name": "TestMomentum",
        "description": "EMA cross strategy",
        "strategy_type": "custom",
        "parameters": {"fast": 9, "slow": 21},
        "code": "def evaluate(candles, volumes, regime): pass",
    }
    r = client.post("/api/strategies", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "TestMomentum"
    assert data["source"] == "manual"
    assert "id" in data
    return data["id"]


def test_get_update_delete(client):
    payload = {"name": "TmpX", "description": "tmp"}
    r = client.post("/api/strategies", json=payload)
    sid = r.json()["id"]

    r2 = client.get(f"/api/strategies/{sid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "TmpX"

    r3 = client.put(f"/api/strategies/{sid}", json={"name": "TmpX-Edited", "weight": 0.5})
    assert r3.status_code == 200
    assert r3.json()["name"] == "TmpX-Edited"
    assert r3.json()["weight"] == 0.5

    r4 = client.delete(f"/api/strategies/{sid}")
    assert r4.status_code == 204


def test_clone(client):
    payload = {"name": "OrigS", "description": "src"}
    r = client.post("/api/strategies", json=payload)
    sid = r.json()["id"]

    r2 = client.post(f"/api/strategies/{sid}/clone")
    assert r2.status_code == 201
    assert r2.json()["name"] == "OrigS (copy)"
    assert r2.json()["source"] == "manual"


def test_export_import_roundtrip(client):
    payload = {"name": "ExportSrc", "parameters": {"k": 14}, "code": "x = 1"}
    r = client.post("/api/strategies", json=payload)
    sid = r.json()["id"]

    r2 = client.get(f"/api/strategies/{sid}/export")
    assert r2.status_code == 200
    assert "attachment" in r2.headers.get("content-disposition", "")
    body = json.loads(r2.content)
    assert body["name"] == "ExportSrc"
    assert body["schema_version"] == "1.0"

    r3 = client.post("/api/strategies/import", json=body)
    assert r3.status_code == 201
    assert r3.json()["name"] == "ExportSrc"
    assert r3.json()["source"] == "import"


def test_sync_github_status(client):
    r = client.get("/api/strategies/sync-github/status")
    assert r.status_code == 200
    data = r.json()
    assert "enabled" in data
    assert "interval_hours" in data
    assert "github_strategies_count" in data


def test_get_404(client):
    r = client.get("/api/strategies/99999")
    assert r.status_code == 404
