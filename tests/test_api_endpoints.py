"""
Integration Tests: FastAPI Control Plane Endpoints.
"""

from __future__ import annotations

import hashlib
import hmac
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import settings
from src.database.connection import init_db


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["project"] == "Atlas-Quant"
    assert "disclaimer" in data


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert "circuit_breaker_status" in data
    assert "daily_deep_llm_calls_limit" in data
    assert data["daily_deep_llm_calls_limit"] == 20


def test_tradingview_webhook_ingest(client):
    payload = {
        "symbol": "EURUSD",
        "timestamp": "2026-10-26T12:00:00Z",
        "timeframe": "M15",
        "open": 1.0850,
        "high": 1.0865,
        "low": 1.0845,
        "close": 1.0860,
        "volume": 800.0,
        "spread": 0.00015,
    }
    res = client.post("/snapshots", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "INGESTED"
    assert "data_hash" in data


def test_metrics_endpoint(client):
    res = client.get("/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "account" in data
    assert "circuit_status" in data


def test_admin_kill_and_reset(client):
    headers = {"X-API-Key": settings.ADMIN_API_KEY}

    # Kill with wrong token
    res_bad = client.post("/admin/kill", json={"reason": "Test", "admin_token": "WRONG"}, headers=headers)
    assert res_bad.status_code == 403

    # Kill with valid token
    res_kill = client.post(
        "/admin/kill",
        json={"reason": "Emergency Test", "admin_token": settings.ADMIN_EMERGENCY_KILL_TOKEN},
        headers=headers,
    )
    assert res_kill.status_code == 200
    assert res_kill.json()["status"] == "HALTED"

    # Reset circuit breaker
    res_reset = client.post(
        "/admin/reset-circuit-breaker",
        json={"admin_token": settings.ADMIN_RESET_TOKEN},
        headers=headers,
    )
    assert res_reset.status_code == 200
    assert res_reset.json()["status"] == "ACTIVE"


def test_approve_live_endpoint(client):
    headers = {"X-API-Key": settings.ADMIN_API_KEY}
    approved_by = "kheni_quant_officer"
    notes = "Passed 14-day paper soak testing."
    payload_msg = f"{approved_by}:{notes}"
    sig = hmac.new(
        settings.ADMIN_HMAC_SECRET.encode("utf-8"),
        payload_msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    payload = {
        "approved_by": approved_by,
        "digital_signature": f"hmac_sha256:{sig}",
        "notes": notes,
    }
    res = client.post("/admin/approve-live", json=payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "RECORDED"
