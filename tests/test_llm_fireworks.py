"""Unit tests for Fireworks AI provider in LLMAgent."""
import pytest
from src.llm_agent import LLMAgent
from src.config import settings
from src.models import (
    LiquidityWeatherReport,
    ComponentScores,
    WeatherState,
    AgentAction,
)


def test_fireworks_agent_initialization(monkeypatch):
    """Verify that setting FIREWORKS_API_KEY configures the agent for Fireworks AI."""
    monkeypatch.setattr(settings, "fireworks_api_key", "fw_test_key_12345")
    monkeypatch.setattr(settings, "fireworks_model", "accounts/fireworks/models/qwen3p8-max")
    monkeypatch.setattr(settings, "fireworks_base_url", "https://api.fireworks.ai/inference/v1")

    agent = LLMAgent()
    assert agent._provider == "fireworks"
    assert agent._model == "accounts/fireworks/models/qwen3p8-max"
    assert agent._client is not None
    assert str(agent._client.base_url).startswith("https://api.fireworks.ai")


@pytest.mark.asyncio
async def test_fireworks_fallback_template(monkeypatch):
    """Verify template rationale fallback when API key is dummy/offline."""
    monkeypatch.setattr(settings, "fireworks_api_key", "invalid_dummy_key")
    agent = LLMAgent()

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
    # Explain weather will catch error and return structured template rationale
    rationale = await agent.explain_weather(report)
    assert "CLEAR" in rationale
    assert "Full strategy size permitted" in rationale
