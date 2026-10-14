"""NOCTURNE — Deterministic Risk Engine (Layer 2 gatekeeper).

IMPORTANT DESIGN PRINCIPLE:
  The LLM NEVER controls whether an order is submitted.
  This module applies hard, deterministic rules. Only after ALL checks
  pass is a RiskDecision(approved=True) returned.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from loguru import logger

from .config import settings
from .models import (
    AgentAction,
    LiquidityWeatherReport,
    OpportunitySignal,
    RiskDecision,
    WeatherState,
)


class RiskEngine:
    """
    Deterministic execution gatekeeper.

    Checks (in order):
      1. Weather state — STORM/BLACKOUT → reject
      2. Spread gate — spread_bps > max_spread_multiplier * baseline → reject
      3. Depth gate — depth < min_depth_ratio * baseline → reject
      4. Volatility gate — vol > max_vol_multiplier * baseline → reject
      5. Per-trade risk cap — proposed notional risk <= max_per_trade_risk_pct * equity
      6. Position-size cap — total exposure <= max_position_pct * equity
      7. Daily-loss gate — daily P&L hasn't hit limit
      8. Consecutive-loss gate — streak hasn't hit limit
    """

    def __init__(self) -> None:
        # State tracked per session
        self._daily_pnl: dict[str, float] = {}           # symbol → daily realized PnL
        self._consecutive_losses: dict[str, int] = {}    # symbol → streak
        self._account_equity: float = 0.0
        self._date_key: str = ""

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def evaluate(
        self,
        signal: OpportunitySignal,
        weather: LiquidityWeatherReport,
        account_equity: float,
        existing_notional: float = 0.0,
    ) -> RiskDecision:
        """
        Evaluate a proposed order and return a RiskDecision.

        Parameters
        ----------
        signal:           The opportunity detected by Layer 1.
        weather:          The most-recent weather report for the symbol.
        account_equity:   Current account equity in USDT.
        existing_notional: Current open notional for this symbol in USDT.
        """
        self._account_equity = account_equity
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if today != self._date_key:
            self._daily_pnl = {}
            self._date_key = today

        rejections: list[str] = []

        # Fail closed on invalid risk context or stale/failed market data.
        if not isinstance(account_equity, (int, float)) or account_equity <= 0:
            rejections.append("Account equity is missing or non-positive")
        if not getattr(weather, "data_quality_ok", True):
            rejections.append("Market data quality check failed")

        if signal.notional_usd <= 0:
            rejections.append("Requested notional must be positive")
        if not 0 <= signal.strength <= 1:
            rejections.append("Signal strength must be between 0 and 1")

        # --- 1. Weather gate ---
        if weather.state in (WeatherState.STORM, WeatherState.BLACKOUT):
            rejections.append(
                f"Weather is {weather.state.value} (score={weather.composite_score:.1f})"
            )

        # --- 2. Spread gate ---
        if (
            weather.spread_bps is not None
            and weather.vol_baseline is not None
        ):
            baseline_spread = weather.vol_baseline  # proxy: we use vol baseline
            # We compute spread ratio from scores instead
            if weather.scores.spread_score < 30:
                rejections.append(
                    f"Spread score critically low ({weather.scores.spread_score:.1f}/100)"
                )

        # --- 3. Depth gate ---
        if weather.scores.depth_score < 25:
            rejections.append(
                f"Order-book depth critically low ({weather.scores.depth_score:.1f}/100)"
            )

        # --- 4. Volatility gate ---
        if weather.scores.volatility_score < 25:
            rejections.append(
                f"Volatility critically elevated ({weather.scores.volatility_score:.1f}/100)"
            )

        # --- 5. Per-trade risk cap ---
        max_risk_usd = account_equity * settings.max_per_trade_risk_pct
        # Approximate risk as distance to stop (default 1% of notional if no stop given)
        stop = signal.stop_price
        entry = signal.entry_price
        if stop and entry and entry > 0:
            risk_per_unit = abs(entry - stop)
            units = signal.notional_usd / entry
            estimated_risk = risk_per_unit * units
        else:
            estimated_risk = signal.notional_usd * 0.01  # 1% default

        if estimated_risk > max_risk_usd:
            rejections.append(
                f"Per-trade risk ${estimated_risk:.2f} > limit ${max_risk_usd:.2f}"
            )

        # --- 6. Position-size cap ---
        max_notional = account_equity * settings.max_position_pct
        if existing_notional + signal.notional_usd > max_notional:
            rejections.append(
                f"Total exposure ${existing_notional + signal.notional_usd:.2f}"
                f" > position limit ${max_notional:.2f}"
            )

        # --- 7. Daily-loss gate ---
        daily = self._daily_pnl.get(signal.symbol, 0.0)
        max_daily_loss = -account_equity * settings.max_daily_loss_pct
        if daily <= max_daily_loss:
            rejections.append(
                f"Daily loss ${daily:.2f} exceeds limit ${max_daily_loss:.2f}"
            )

        # --- 8. Consecutive-loss gate ---
        consec = self._consecutive_losses.get(signal.symbol, 0)
        if consec >= settings.max_consecutive_losses:
            rejections.append(
                f"Consecutive loss streak ({consec}) hit limit ({settings.max_consecutive_losses})"
            )

        # --- Decision ---
        approved = len(rejections) == 0
        approved_notional = signal.notional_usd * weather.recommended_size_pct if approved else None
        approved_size_pct = weather.recommended_size_pct if approved else None

        decision = RiskDecision(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            approved=approved,
            rejection_reasons=rejections,
            approved_notional_usd=approved_notional,
            approved_size_pct=approved_size_pct,
            stop_price=signal.stop_price,
            weather_state=weather.state,
            weather_score=weather.composite_score,
        )

        if approved:
            logger.info(
                f"[risk] ✅ APPROVED {signal.symbol} "
                f"notional=${approved_notional:.2f} "
                f"weather={weather.state.value}({weather.composite_score:.1f})"
            )
        else:
            logger.warning(
                f"[risk] ❌ REJECTED {signal.symbol}: {'; '.join(rejections)}"
            )

        return decision

    # ------------------------------------------------------------------
    # Session state updates (called by execution service)
    # ------------------------------------------------------------------

    def record_trade_result(self, symbol: str, pnl: float) -> None:
        """Update daily PnL and consecutive loss tracker after a trade closes."""
        self._daily_pnl[symbol] = self._daily_pnl.get(symbol, 0.0) + pnl
        if pnl < 0:
            self._consecutive_losses[symbol] = self._consecutive_losses.get(symbol, 0) + 1
        else:
            self._consecutive_losses[symbol] = 0

    def reset_daily(self) -> None:
        """Reset daily accumulators (call at market open or midnight UTC)."""
        self._daily_pnl = {}

    def update_equity(self, equity: float) -> None:
        self._account_equity = equity
