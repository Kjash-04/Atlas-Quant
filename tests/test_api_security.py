"""
Regression Tests: API Security & Resilience (R-1 through R-5).
Verifies:
  - Fail-closed API key and admin token authentication (R-1, R-3)
  - Mandatory HMAC signature check for live trading authorization (R-2)
  - Rejection of old public default secrets (R-3)
  - Background broker heartbeat ticker keeping broker heartbeat fresh (R-4)
  - Honest uuid fallback reporting '0.10.0+stdlib-fallback' (R-5)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import subprocess
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import Settings, settings
from src.database.connection import init_db
from src.risk_engine.engine import risk_engine


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


# 1. Unauthenticated /admin/kill -> 401
def test_unauthenticated_admin_kill_returns_401(client):
    res = client.post("/admin/kill", json={"reason": "Audit", "admin_token": "some_token"})
    assert res.status_code == 401
    assert "unauthorized" in res.json().get("detail", "").lower()


# 2. /admin/reset-circuit-breaker -> 401
def test_unauthenticated_admin_reset_circuit_breaker_returns_401(client):
    res = client.post("/admin/reset-circuit-breaker", json={"admin_token": "some_token"})
    assert res.status_code == 401
    assert "unauthorized" in res.json().get("detail", "").lower()


# 3. POST /orders -> 401
def test_unauthenticated_post_orders_returns_401(client):
    payload = {
        "symbol": "EURUSD",
        "side": "BUY",
        "order_type": "MARKET",
        "lots": 0.1,
        "strategy_id": "strat-test-01",
    }
    res = client.post("/orders", json=payload)
    assert res.status_code == 401
    assert "unauthorized" in res.json().get("detail", "").lower()


# 4. Wrong API key -> 401
def test_wrong_api_key_returns_401(client):
    headers = {"X-API-Key": "incorrect_or_forged_key"}
    res = client.post(
        "/admin/kill",
        json={"reason": "Audit", "admin_token": "some_token"},
        headers=headers,
    )
    assert res.status_code == 401
    assert "unauthorized" in res.json().get("detail", "").lower()


# 5. Old public default literals rejected with 403
def test_old_public_literals_rejected_with_403(client):
    headers = {"X-API-Key": settings.ADMIN_API_KEY}

    # Attempt kill with old public default literal
    res_kill = client.post(
        "/admin/kill",
        json={"reason": "Audit", "admin_token": "EMERGENCY_KILL_AUTHORIZED"},
        headers=headers,
    )
    assert res_kill.status_code == 403

    # Attempt reset with old public default literal
    res_reset = client.post(
        "/admin/reset-circuit-breaker",
        json={"admin_token": "ADMIN_RESET_CONFIRMED"},
        headers=headers,
    )
    assert res_reset.status_code == 403


# 6. Non-HMAC signature -> 400
def test_approve_live_non_hmac_signature_returns_400(client):
    headers = {"X-API-Key": settings.ADMIN_API_KEY}
    payload = {
        "approved_by": "officer",
        "digital_signature": "0123456789abcdef",
        "notes": "14-day paper soak passed",
    }
    res = client.post("/admin/approve-live", json=payload, headers=headers)
    assert res.status_code == 400
    assert "hmac_sha256" in res.json().get("detail", "").lower()


# 7. Wrong digest -> 400
def test_approve_live_wrong_digest_returns_400(client):
    headers = {"X-API-Key": settings.ADMIN_API_KEY}
    payload = {
        "approved_by": "officer",
        "digital_signature": "hmac_sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "notes": "14-day paper soak passed",
    }
    res = client.post("/admin/approve-live", json=payload, headers=headers)
    assert res.status_code == 400
    assert "verification failed" in res.json().get("detail", "").lower()


# 8. Signature reused for a different approved_by -> 400
def test_approve_live_signature_reused_for_different_user_returns_400(client):
    headers = {"X-API-Key": settings.ADMIN_API_KEY}
    msg = "officer1:14-day paper soak passed"
    sig = hmac.new(
        settings.ADMIN_HMAC_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    payload = {
        "approved_by": "officer2",  # Different user from signature
        "digital_signature": f"hmac_sha256:{sig}",
        "notes": "14-day paper soak passed",
    }
    res = client.post("/admin/approve-live", json=payload, headers=headers)
    assert res.status_code == 400
    assert "verification failed" in res.json().get("detail", "").lower()


# 9. Valid HMAC -> 200
def test_approve_live_valid_hmac_returns_200(client):
    headers = {"X-API-Key": settings.ADMIN_API_KEY}
    approved_by = "officer"
    notes = "14-day paper soak passed"
    msg = f"{approved_by}:{notes}"
    sig = hmac.new(
        settings.ADMIN_HMAC_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    payload = {
        "approved_by": approved_by,
        "digital_signature": f"hmac_sha256:{sig}",
        "notes": notes,
    }
    res = client.post("/admin/approve-live", json=payload, headers=headers)
    assert res.status_code == 200
    assert res.json().get("status") == "RECORDED"


# 10. Uppercase hex -> 200
def test_approve_live_uppercase_hex_returns_200(client):
    headers = {"X-API-Key": settings.ADMIN_API_KEY}
    approved_by = "officer"
    notes = "14-day paper soak passed - uppercase hex"
    msg = f"{approved_by}:{notes}"
    sig = hmac.new(
        settings.ADMIN_HMAC_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()

    payload = {
        "approved_by": approved_by,
        "digital_signature": f"hmac_sha256:{sig}",
        "notes": notes,
    }
    res = client.post("/admin/approve-live", json=payload, headers=headers)
    assert res.status_code == 200
    assert res.json().get("status") == "RECORDED"


# 11. No public default secrets in settings
def test_no_public_default_secrets_in_settings():
    old_literals = {
        "EMERGENCY_KILL_AUTHORIZED",
        "ADMIN_RESET_CONFIRMED",
        "atlas_quant_admin_hmac_secret_2026",
        "atlas_live_trading_secret_key_2026",
    }
    assert settings.ADMIN_EMERGENCY_KILL_TOKEN not in old_literals
    assert settings.ADMIN_RESET_TOKEN not in old_literals
    assert settings.ADMIN_HMAC_SECRET not in old_literals

    # With empty environment, Settings must have empty string defaults without fallbacks
    with patch.dict(os.environ, {}, clear=True):
        clean_settings = Settings()
        assert clean_settings.ADMIN_API_KEY == ""
        assert clean_settings.ADMIN_EMERGENCY_KILL_TOKEN == ""
        assert clean_settings.ADMIN_RESET_TOKEN == ""
        assert clean_settings.ADMIN_HMAC_SECRET == ""


# 12. Heartbeat stays < 60 s old with no /health calls
def test_heartbeat_stays_fresh_without_health_calls(client):
    # With TestClient running lifespan, background heartbeat updates risk_engine
    now = datetime.now(timezone.utc)
    age = (now - risk_engine.last_broker_heartbeat_utc).total_seconds()
    assert age < 60.0


# 13. uuid fallback does not claim a real version
def test_uuid_fallback_does_not_claim_real_version():
    from src._uuid_compat import _create_fallback_module, _UUIDCompatFinder

    fallback_mod = _create_fallback_module("uuid_utils")
    assert fallback_mod.__version__ == "0.10.0+stdlib-fallback"
    assert fallback_mod.IS_STDLIB_FALLBACK is True

    # Check fallback disable environment variable
    finder = _UUIDCompatFinder()
    with patch.dict(os.environ, {"ATLAS_UUID_DISABLE_FALLBACK": "1"}):
        assert finder.find_spec("uuid_utils") is None


# 14. uuid fallback when compiled extension is blocked
def test_uuid_fallback_when_compiled_extension_is_blocked():
    """Subprocess test simulating compiled extension blocked by AppLocker/WDAC.
    Reproduces failure without poisoning other tests in the runner.
    """
    code = """
import sys
import importlib

# Simulate compiled extension failing to load
sys.modules['uuid_utils._uuid_utils'] = None
sys.modules.pop('uuid_utils', None)
sys.modules.pop('uuid_utils.compat', None)

from src._uuid_compat import install_uuid_compat, UUID_STDLIB_FALLBACK_ACTIVE
import src._uuid_compat as compat_mod

active = install_uuid_compat()
assert compat_mod.UUID_STDLIB_FALLBACK_ACTIVE is True

import uuid_utils
assert uuid_utils.__version__ == '0.10.0+stdlib-fallback'
assert uuid_utils.IS_STDLIB_FALLBACK is True

from langchain_core.utils.uuid import uuid7 as lc_uuid7
u1 = lc_uuid7()
assert u1 is not None

from langsmith._internal._uuid import uuid7 as ls_uuid7
u2 = ls_uuid7()
assert u2 is not None

from langgraph.graph import StateGraph
assert StateGraph is not None

from src.self_improvement.orchestrator import SelfImprovementOrchestrator
assert SelfImprovementOrchestrator is not None

print('OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Subprocess failed:\n{result.stderr}\n{result.stdout}"
    assert "OK" in result.stdout

