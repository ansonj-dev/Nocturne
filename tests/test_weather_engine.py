"""Unit tests for NOCTURNE Liquidity Weather Engine."""
import pytest
from src.models import (
    ComponentScores,
    LiquidityWeatherReport,
    WeatherState,
    AgentAction,
)
from src.config import settings


def test_component_score_bounds():
    """Verify component scores stay strictly within 0-100 range."""
    scores = ComponentScores(
        spread_score=100.0,
        depth_score=50.0,
        volatility_score=0.0,
        lead_lag_score=75.0,
        event_score=80.0,
    )
    assert 0 <= scores.spread_score <= 100
    assert 0 <= scores.depth_score <= 100
    assert 0 <= scores.volatility_score <= 100


def test_weather_state_mapping():
    """Verify composite score thresholds correctly map to 4-state regimes."""
    # CLEAR >= 70.0
    s_clear = 75.0
    assert s_clear >= settings.clear_threshold

    # CLOUDY: 45.0 <= s < 70.0
    s_cloudy = 55.0
    assert settings.cloudy_threshold <= s_cloudy < settings.clear_threshold

    # STORM: 20.0 <= s < 45.0
    s_storm = 30.0
    assert settings.storm_threshold <= s_storm < settings.cloudy_threshold

    # BLACKOUT: < 20.0
    s_blackout = 15.0
    assert s_blackout < settings.storm_threshold


def test_weather_report_creation():
    """Verify LiquidityWeatherReport instantiation and properties."""
    report = LiquidityWeatherReport(
        symbol="AAPLUSDT",
        scores=ComponentScores(
            spread_score=90.0,
            depth_score=85.0,
            volatility_score=80.0,
            lead_lag_score=70.0,
            event_score=85.0,
        ),
        composite_score=83.5,
        state=WeatherState.CLEAR,
        action=AgentAction.TRADE,
        recommended_size_pct=1.0,
        bid=189.5,
        ask=189.55,
        mid=189.525,
        spread_bps=2.6,
        depth_within_25bps=120_000,
        realized_vol_1h=22.0,
        rationale="CLEAR weather test",
    )
    assert report.state == WeatherState.CLEAR
    assert report.action == AgentAction.TRADE
    assert report.recommended_size_pct == 1.0
    assert report.composite_score == 83.5
