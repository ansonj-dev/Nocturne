"""NOCTURNE — LLM Rationale Agent.

The LLM's ONLY job is to explain regime changes in human-readable language.
It has NO authority over whether an order is placed — that belongs exclusively
to the RiskEngine.
"""
from __future__ import annotations

from typing import Optional

from loguru import logger

from .config import settings
from .models import LiquidityWeatherReport, RiskDecision, OpportunitySignal


_SYSTEM_PROMPT = """\
You are NOCTURNE's market-regime analyst. Explain the supplied liquidity \
metrics for a tokenised U.S. stock in clear, concise language (80 words max). \
Use only facts and values in the prompt; do not invent causes, catalysts, \
predictions, or market data. Format the response as Markdown with a bold \
weather-and-score heading, a short summary, a 'Key drivers' heading with a \
short bullet list, and a 'System action' heading. Describe TRADE, REDUCE, WAIT, \
or STAND_DOWN only as the deterministic risk engine's status, not as your own \
advice. Never recommend buying, selling, opening a position, or a position size. \
Do not promise profits or give financial advice.\
"""


class LLMAgent:
    """
    Thin wrapper that calls the configured LLM to generate rationale text.
    Falls back to a template string if the API call fails.
    """

    def __init__(self) -> None:
        # Auto-detect Fireworks if FIREWORKS_API_KEY is provided
        if settings.fireworks_api_key and settings.llm_provider in ("openai", "fireworks"):
            self._provider = "fireworks"
            self._model = settings.fireworks_model
        else:
            self._provider = settings.llm_provider
            self._model = settings.llm_model

        self._client = self._build_client()
        logger.info(
            f"[llm] configured provider={self._provider} model={self._model} "
            f"client_ready={self._client is not None}"
        )

    def _build_client(self):
        if self._provider == "fireworks":
            try:
                import openai
                return openai.AsyncOpenAI(
                    api_key=settings.fireworks_api_key,
                    base_url=settings.fireworks_base_url,
                )
            except Exception as exc:
                logger.warning(f"[llm] Failed to initialize Fireworks client: {exc}")
                return None
        elif self._provider == "anthropic":
            try:
                import anthropic
                return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            except Exception:
                return None
        else:
            try:
                import openai
                return openai.AsyncOpenAI(api_key=settings.openai_api_key)
            except Exception:
                return None

    async def explain_weather(self, report: LiquidityWeatherReport) -> str:
        """Generate a human-readable rationale for the weather report."""
        prompt = self._build_weather_prompt(report)
        try:
            rationale = await self._call_llm(prompt)
            if rationale:
                return rationale
            logger.warning("[llm] Fireworks returned an empty rationale, using template")
        except Exception as exc:
            logger.warning(f"[llm] LLM call failed, using template: {exc}")
        return self._template_rationale(report)

    async def explain_rejection(
        self, signal: OpportunitySignal, decision: RiskDecision
    ) -> str:
        """Explain why a trade was rejected in plain language."""
        reasons = "; ".join(decision.rejection_reasons) or "risk limits exceeded"
        prompt = (
            f"A trading signal for {signal.symbol} ({signal.signal_type.value}) "
            f"was REJECTED by the risk engine. Reasons: {reasons}. "
            f"Weather score: {decision.weather_score:.1f}/100 ({decision.weather_state.value}). "
            "Explain this to the trader in 2-3 sentences."
        )
        try:
            return await self._call_llm(prompt)
        except Exception as exc:
            logger.warning(f"[llm] LLM rejection explain failed: {exc}")
            return f"Trade rejected: {reasons}"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_weather_prompt(self, report: LiquidityWeatherReport) -> str:
        s = report.scores
        lines = [
            f"Symbol: {report.symbol}",
            f"Liquidity Weather: {report.state.value} (score {report.composite_score:.1f}/100)",
            f"Recommendation: {report.action.value}",
            f"  Spread score:     {s.spread_score:.1f}/100"
            + (f" (spread {report.spread_bps:.1f} bps)" if report.spread_bps else ""),
            f"  Depth score:      {s.depth_score:.1f}/100"
            + (f" (depth ${report.depth_within_25bps:,.0f})" if report.depth_within_25bps else ""),
            f"  Volatility score: {s.volatility_score:.1f}/100"
            + (f" (vol {report.realized_vol_1h:.1f}% ann.)" if report.realized_vol_1h else ""),
            f"  Lead-lag score:   {s.lead_lag_score:.1f}/100",
            f"  Event score:      {s.event_score:.1f}/100",
            f"Allowed position size: {report.recommended_size_pct*100:.0f}% of normal",
        ]
        return "Given these live market conditions, write the rationale:\n\n" + "\n".join(lines)

    async def _call_llm(self, user_prompt: str) -> str:
        if self._client is None:
            raise RuntimeError("LLM client not initialised — check API keys in .env")

        if self._provider == "anthropic":
            import anthropic
            msg = await self._client.messages.create(
                model=self._model or "claude-3-haiku-20240307",
                max_tokens=200,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return msg.content[0].text.strip()
        else:
            default_m = "accounts/fireworks/models/qwen3p8-max" if self._provider == "fireworks" else "gpt-4o-mini"
            msg = await self._client.chat.completions.create(
                model=self._model or default_m,
                max_tokens=4000 if self._provider == "fireworks" else 200,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                **({"extra_body": {"reasoning_effort": "none"}} if self._provider == "fireworks" else {}),
            )
            return (msg.choices[0].message.content or "").strip()

    @staticmethod
    def _template_rationale(report: LiquidityWeatherReport) -> str:
        """Fallback template when LLM is unavailable."""
        s = report.scores
        drivers = []
        if s.spread_score < 50:
            drivers.append(f"spread elevated ({s.spread_score:.0f}/100)")
        if s.depth_score < 50:
            drivers.append(f"thin order book ({s.depth_score:.0f}/100)")
        if s.volatility_score < 50:
            drivers.append(f"high volatility ({s.volatility_score:.0f}/100)")
        driver_text = ", ".join(drivers) if drivers else "conditions within normal range"

        action_text = {
            "TRADE": "Full strategy size permitted.",
            "REDUCE": f"Reduce position to {report.recommended_size_pct*100:.0f}% of normal and tighten stops.",
            "WAIT": "Do not open new positions; manage existing risk.",
            "STAND_DOWN": "Cancel pending orders and stand down immediately.",
        }.get(report.action.value, "")

        return (
            f"Liquidity Weather: {report.state.value} (score {report.composite_score:.1f}/100). "
            f"Key driver(s): {driver_text}. "
            f"{action_text}"
        )
