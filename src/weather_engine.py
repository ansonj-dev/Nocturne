"""NOCTURNE — Liquidity Weather Engine (Layer 2 — Execution Gatekeeper).

Computes the five-component Liquidity Weather Score and maps it to a
four-state regime: CLEAR | CLOUDY | STORM | BLACKOUT.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
import pandas as pd
from loguru import logger

from .bitget_client import BitgetClient
from .config import settings
from .models import (
    AgentAction,
    ComponentScores,
    LiquidityWeatherReport,
    WeatherState,
)


# ---------------------------------------------------------------------------
# Helper: annualised realised volatility from a list of close prices
# ---------------------------------------------------------------------------

def _realised_vol_annualised(closes: list[float], periods_per_year: int = 8760) -> float:
    """Returns annualised realised vol from a list of close prices."""
    if len(closes) < 2:
        return 0.0
    arr = np.array(closes, dtype=float)
    log_rets = np.diff(np.log(arr + 1e-12))
    return float(np.std(log_rets, ddof=1) * math.sqrt(periods_per_year) * 100)


def _depth_within_bps(bids: list, asks: list, mid: float, bps: float = 25.0) -> float:
    """Compute total USDT notional within ±bps of mid price."""
    threshold = mid * bps / 10_000
    total = 0.0
    for price_str, size_str in bids:
        p = float(price_str)
        if mid - p <= threshold:
            total += float(price_str) * float(size_str)
    for price_str, size_str in asks:
        p = float(price_str)
        if p - mid <= threshold:
            total += float(price_str) * float(size_str)
    return total


# ---------------------------------------------------------------------------
# Main engine class
# ---------------------------------------------------------------------------


class LiquidityWeatherEngine:
    """
    Computes a composite Liquidity Weather Score (0-100) and regime state
    for a given tokenized-stock symbol.

    Score = w1*S_spread + w2*S_depth + w3*S_vol + w4*S_leadlag + w5*S_event

    Each component is clamped [0, 100]:
      - 100 = ideal / no risk
      -   0 = worst case / maximum risk
    """

    def __init__(self, client: BitgetClient) -> None:
        self._client = client

        # Rolling baselines per symbol: {symbol: {"spread_median": float, ...}}
        self._baselines: dict[str, dict[str, float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate(self, symbol: str) -> LiquidityWeatherReport:
        """Run a full weather evaluation for *symbol*."""
        try:
            ticker = await self._client.get_ticker(symbol)
            orderbook = await self._client.get_orderbook(symbol, limit=50)
            klines = await self._client.get_klines(symbol, granularity="1H", limit=100)
            data_ok = True
        except Exception as exc:
            logger.warning(f"[weather] Data fetch failed for {symbol}: {exc}")
            return self._blackout_report(symbol, f"Data fetch failed: {exc}")

        # --- Parse ticker ---
        try:
            bid = float(ticker.get("bidPr", 0) or ticker.get("bestBid", 0))
            ask = float(ticker.get("askPr", 0) or ticker.get("bestAsk", 0))
            last = float(ticker.get("lastPr", 0) or ticker.get("last", 0))
            mid = (bid + ask) / 2 if bid and ask else last
            spread_bps = ((ask - bid) / mid * 10_000) if mid > 0 else 9999.0
        except Exception as exc:
            logger.warning(f"[weather] Ticker parse failed for {symbol}: {exc}")
            return self._blackout_report(symbol, f"Ticker parse failed: {exc}")

        # --- Data quality gate ---
        if mid <= 0 or spread_bps >= 500:
            return self._blackout_report(symbol, f"Extreme spread ({spread_bps:.1f} bps) or zero price")

        # --- Parse order book ---
        bids_raw = orderbook.get("bids", [])
        asks_raw = orderbook.get("asks", [])
        depth_25bps = _depth_within_bps(bids_raw, asks_raw, mid, bps=25.0)

        # --- Parse klines for vol ---
        closes = [float(k[4]) for k in klines if k and len(k) >= 5]
        vol_1h = _realised_vol_annualised(closes[-30:]) if closes else 0.0  # 30-bar window

        # --- Update / read baselines ---
        baseline = self._get_baseline(symbol, spread_bps, depth_25bps, vol_1h)

        # --- Score each component (100 = best) ---
        spread_score = self._score_spread(spread_bps, baseline["spread_median"])
        depth_score = self._score_depth(depth_25bps, baseline["depth_median"])
        vol_score = self._score_vol(vol_1h, baseline["vol_median"])
        lead_lag_score = 70.0  # Placeholder: would require reference-asset feed
        event_score = 80.0     # Placeholder: would require event calendar feed

        composite = (
            settings.weight_spread * spread_score
            + settings.weight_depth * depth_score
            + settings.weight_volatility * vol_score
            + settings.weight_lead_lag * lead_lag_score
            + settings.weight_event * event_score
        )
        composite = max(0.0, min(100.0, composite))

        state, action, size_pct = self._classify(composite)

        scores = ComponentScores(
            spread_score=spread_score,
            depth_score=depth_score,
            volatility_score=vol_score,
            lead_lag_score=lead_lag_score,
            event_score=event_score,
        )

        return LiquidityWeatherReport(
            symbol=symbol,
            scores=scores,
            composite_score=composite,
            state=state,
            action=action,
            recommended_size_pct=size_pct,
            bid=bid,
            ask=ask,
            mid=mid,
            spread_bps=spread_bps,
            depth_within_25bps=depth_25bps,
            realized_vol_1h=vol_1h,
            vol_baseline=baseline["vol_median"],
            data_quality_ok=True,
        )

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _score_spread(self, current_bps: float, median_bps: float) -> float:
        """100 = at/below median; 0 = 5x+ median."""
        if median_bps <= 0:
            return 50.0
        ratio = current_bps / max(median_bps, 0.1)
        # Linear ramp: ratio 1→score 100, ratio 5→score 0
        score = 100.0 - (ratio - 1.0) * 25.0
        return max(0.0, min(100.0, score))

    def _score_depth(self, current_depth: float, median_depth: float) -> float:
        """100 = at/above median; 0 = 0% of median."""
        if median_depth <= 0:
            return 50.0
        ratio = current_depth / max(median_depth, 1.0)
        score = ratio * 100.0
        return max(0.0, min(100.0, score))

    def _score_vol(self, current_vol: float, median_vol: float) -> float:
        """100 = at/below median; 0 = 3x+ median."""
        if median_vol <= 0:
            return 50.0
        ratio = current_vol / max(median_vol, 0.01)
        score = 100.0 - (ratio - 1.0) * 50.0
        return max(0.0, min(100.0, score))

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify(
        self, score: float
    ) -> tuple[WeatherState, AgentAction, float]:
        if score >= settings.clear_threshold:
            return WeatherState.CLEAR, AgentAction.TRADE, 1.0
        elif score >= settings.cloudy_threshold:
            size = 0.3 + (score - settings.cloudy_threshold) / (settings.clear_threshold - settings.cloudy_threshold) * 0.7
            return WeatherState.CLOUDY, AgentAction.REDUCE, round(size, 2)
        elif score >= settings.storm_threshold:
            return WeatherState.STORM, AgentAction.WAIT, 0.0
        else:
            return WeatherState.BLACKOUT, AgentAction.STAND_DOWN, 0.0

    # ------------------------------------------------------------------
    # Baselines
    # ------------------------------------------------------------------

    def _get_baseline(
        self,
        symbol: str,
        spread_bps: float,
        depth: float,
        vol: float,
    ) -> dict[str, float]:
        """Maintain simple exponential moving averages as baselines."""
        alpha = 0.05  # slow EMA for stability
        if symbol not in self._baselines:
            self._baselines[symbol] = {
                "spread_median": spread_bps,
                "depth_median": max(depth, 1.0),
                "vol_median": max(vol, 0.01),
            }
        else:
            b = self._baselines[symbol]
            b["spread_median"] = (1 - alpha) * b["spread_median"] + alpha * spread_bps
            b["depth_median"] = (1 - alpha) * b["depth_median"] + alpha * max(depth, 1.0)
            b["vol_median"] = (1 - alpha) * b["vol_median"] + alpha * max(vol, 0.01)
        return self._baselines[symbol]

    # ------------------------------------------------------------------
    # BLACKOUT report factory
    # ------------------------------------------------------------------

    def _blackout_report(self, symbol: str, reason: str) -> LiquidityWeatherReport:
        return LiquidityWeatherReport(
            symbol=symbol,
            scores=ComponentScores(
                spread_score=0,
                depth_score=0,
                volatility_score=0,
                lead_lag_score=0,
                event_score=0,
            ),
            composite_score=0.0,
            state=WeatherState.BLACKOUT,
            action=AgentAction.STAND_DOWN,
            recommended_size_pct=0.0,
            data_quality_ok=False,
            rationale=f"BLACKOUT — {reason}",
        )
