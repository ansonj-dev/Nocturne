"""Unit tests for NOCTURNE Deterministic Risk Engine (8-check execution gatekeeper)."""
import pytest
from src.risk_engine import RiskEngine
from src.models import (
    OpportunitySignal,
    SignalType,
    OrderSide,
    WeatherState,
    AgentAction,
    ComponentScores,
    LiquidityWeatherReport,
)


@pytest.fixture
def risk_engine():
    return RiskEngine()


@pytest.fixture
def clear_weather():
    return LiquidityWeatherReport(
        symbol="AAPLUSDT",
        scores=ComponentScores(
            spread_score=85.0,
            depth_score=80.0,
            volatility_score=75.0,
            lead_lag_score=70.0,
            event_score=80.0,
        ),
        composite_score=79.0,
        state=WeatherState.CLEAR,
        action=AgentAction.TRADE,
        recommended_size_pct=1.0,
        bid=189.5,
        ask=189.55,
        mid=189.525,
        spread_bps=2.6,
        depth_within_25bps=150_000,
        realized_vol_1h=20.0,
    )


@pytest.fixture
def storm_weather():
    return LiquidityWeatherReport(
        symbol="AAPLUSDT",
        scores=ComponentScores(
            spread_score=20.0,
            depth_score=15.0,
            volatility_score=20.0,
            lead_lag_score=40.0,
            event_score=30.0,
        ),
        composite_score=22.0,
        state=WeatherState.STORM,
        action=AgentAction.STAND_DOWN,
        recommended_size_pct=0.0,
        bid=188.0,
        ask=190.0,
        mid=189.0,
        spread_bps=105.0,
        depth_within_25bps=12_000,
        realized_vol_1h=65.0,
    )


def test_storm_weather_rejection(risk_engine, storm_weather):
    """Rule 1: STORM weather must unconditionally reject proposed orders."""
    signal = OpportunitySignal(
        symbol="AAPLUSDT",
        signal_type=SignalType.MEAN_REVERSION,
        direction=OrderSide.LONG,
        strength=0.8,
        notional_usd=100.0,
        entry_price=189.0,
        stop_price=187.0,
    )
    decision = risk_engine.evaluate(signal=signal, weather=storm_weather, account_equity=10_000.0)
    assert not decision.approved
    assert any("Weather is STORM" in r for r in decision.rejection_reasons)


def test_clear_weather_approval(risk_engine, clear_weather):
    """When all risk checks pass, order must be APPROVED with full or scaled notional."""
    signal = OpportunitySignal(
        symbol="AAPLUSDT",
        signal_type=SignalType.MEAN_REVERSION,
        direction=OrderSide.LONG,
        strength=0.8,
        notional_usd=200.0,  # 2% of 10,000 equity (within 5% max position)
        entry_price=189.52,
        stop_price=188.0,    # risk is ~1.52/189.52 * 200 = ~$1.60 (well within $50 risk cap)
    )
    decision = risk_engine.evaluate(signal=signal, weather=clear_weather, account_equity=10_000.0)
    assert decision.approved
    assert decision.approved_notional_usd == 200.0


def test_position_limit_exceeded(risk_engine, clear_weather):
    """Rule 6: Reject when total position exposure exceeds max_position_pct (5%)."""
    signal = OpportunitySignal(
        symbol="AAPLUSDT",
        signal_type=SignalType.MEAN_REVERSION,
        direction=OrderSide.LONG,
        strength=0.8,
        notional_usd=800.0,  # 800 > 5% of 10,000 ($500)
        entry_price=189.52,
        stop_price=189.0,
    )
    decision = risk_engine.evaluate(signal=signal, weather=clear_weather, account_equity=10_000.0)
    assert not decision.approved
    assert any("position limit" in r for r in decision.rejection_reasons)


def test_consecutive_losses_limit(risk_engine, clear_weather):
    """Rule 8: Consecutive losing trades trigger cooldown circuit breaker."""
    symbol = "AAPLUSDT"
    # Record 3 consecutive losses (default threshold)
    risk_engine.record_trade_result(symbol, -50.0)
    risk_engine.record_trade_result(symbol, -40.0)
    risk_engine.record_trade_result(symbol, -30.0)

    signal = OpportunitySignal(
        symbol=symbol,
        signal_type=SignalType.MEAN_REVERSION,
        direction=OrderSide.LONG,
        strength=0.8,
        notional_usd=100.0,
        entry_price=189.52,
        stop_price=188.0,
    )
    decision = risk_engine.evaluate(signal=signal, weather=clear_weather, account_equity=10_000.0)
    assert not decision.approved
    assert any("Consecutive loss streak" in r for r in decision.rejection_reasons)
