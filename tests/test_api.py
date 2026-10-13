"""Integration tests for NOCTURNE FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from src.api import app

def test_health_endpoint():
    """Verify health endpoint responds 200 with version info."""
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


def test_evaluate_signal_endpoint():
    """Verify POST /signal returns deterministic risk engine decision."""
    with TestClient(app) as client:
        payload = {
            "symbol": "AAPLUSDT",
            "signal_type": "MEAN_REVERSION",
            "direction": "long",
            "strength": 0.85,
            "notional_usd": 150.0,
            "account_equity": 5000.0,
        }
        response = client.post("/signal", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "decision" in data
        assert "approved" in data["decision"]
        assert "weather" in data
        assert "rationale" in data
