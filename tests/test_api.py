"""Integration tests for NOCTURNE FastAPI endpoints."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
import src.api as api
from src.api import app
from src.models import (
    AgentAction,
    ComponentScores,
    LiquidityWeatherReport,
    WeatherState,
)

def test_health_endpoint():
    """Verify health endpoint responds 200 with version info."""
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


def test_evaluate_signal_endpoint(monkeypatch):
    """Verify POST /signal with known weather/account data, without live credentials."""
    report = LiquidityWeatherReport(
        symbol="AAPLUSDT",
        scores=ComponentScores(
            spread_score=80.0,
            depth_score=75.0,
            volatility_score=70.0,
            lead_lag_score=80.0,
            event_score=85.0,
        ),
        composite_score=77.0,
        state=WeatherState.CLEAR,
        action=AgentAction.TRADE,
        recommended_size_pct=1.0,
        bid=189.5,
        ask=189.55,
        mid=189.525,
        spread_bps=2.6,
        depth_within_25bps=120_000,
        realized_vol_1h=22.0,
    )

    with TestClient(app) as client:
        monkeypatch.setattr(api._weather_engine, "evaluate", AsyncMock(return_value=report))
        monkeypatch.setattr(
            api._client,
            "get_account_balance",
            AsyncMock(return_value=[{"marginCoin": "USDT", "usdtEquity": "5000"}]),
        )
        monkeypatch.setattr(api._client, "get_positions", AsyncMock(return_value=[]))
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
