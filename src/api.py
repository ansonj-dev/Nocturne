"""NOCTURNE — FastAPI REST + WebSocket backend.

Endpoints:
  GET  /health                       — liveness probe
  GET  /weather/{symbol}             — run a fresh weather check
  GET  /weather/{symbol}/history     — recent weather timeline
  POST /signal                       — submit an opportunity signal for risk evaluation
  GET  /trades                       — recent trade history
  GET  /trades/{symbol}              — per-symbol trade history
  GET  /account                      — live account balance & positions
  WS   /ws/weather/{symbol}          — streaming weather updates (30-sec poll)
"""
from __future__ import annotations

import asyncio
import hmac
import json
import re
import time
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, Field

from .audit_log import (
    get_recent_weather,
    get_trade_history,
    init_db,
    log_decision,
    log_signal,
    log_weather,
)
from .bitget_client import BitgetClient
from .config import settings
from .llm_agent import LLMAgent
from .models import (
    LiquidityWeatherReport,
    OpportunitySignal,
    OrderSide,
    SignalType,
)
from .risk_engine import RiskEngine
from .weather_engine import LiquidityWeatherEngine

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NOCTURNE",
    description="Liquidity-Weather Agent for 24/7 Tokenized U.S. Stocks",
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global singletons (initialised on startup)
_client: Optional[BitgetClient] = None
_weather_engine: Optional[LiquidityWeatherEngine] = None
_risk_engine: Optional[RiskEngine] = None
_llm_agent: Optional[LLMAgent] = None
_symbols_cache: list[dict[str, str]] = []
_symbols_cached_at = 0.0


@app.on_event("startup")
async def startup():
    global _client, _weather_engine, _risk_engine, _llm_agent
    await init_db()
    _client = BitgetClient(sandbox=settings.bitget_use_sandbox)
    _weather_engine = LiquidityWeatherEngine(_client)
    _risk_engine = RiskEngine()
    _llm_agent = LLMAgent()
    logger.info(f"[api] NOCTURNE {settings.app_version} started")


@app.on_event("shutdown")
async def shutdown():
    if _client:
        await _client.close()


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


import os
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

_dashboard_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))
if os.path.exists(_dashboard_path):
    app.mount("/dashboard", StaticFiles(directory=_dashboard_path, html=True), name="dashboard")


@app.get("/", tags=["meta"], include_in_schema=False)
async def root():
    return RedirectResponse(url="/dashboard/")


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "version": settings.app_version}


@app.get("/symbols", tags=["market"])
async def list_symbols():
    """Return the exchange's current Reality stock instruments."""
    global _symbols_cache, _symbols_cached_at
    if _symbols_cache and time.monotonic() - _symbols_cached_at < 300:
        return _symbols_cache
    try:
        _symbols_cache = await _client.list_reality_symbols()
        _symbols_cached_at = time.monotonic()
        return _symbols_cache
    except Exception as exc:
        if _symbols_cache:
            return _symbols_cache
        raise HTTPException(status_code=502, detail=f"Could not load Reality symbols: {exc}") from exc


@app.get("/weather/{symbol}", response_model=LiquidityWeatherReport, tags=["weather"])
async def get_weather(symbol: str, explain: bool = False):
    """
    Run a fresh Liquidity Weather check for *symbol*.
    Set `explain=true` to request an LLM rationale. By default, weather checks
    do not call the LLM, which avoids usage-based AI charges during monitoring.
    """
    symbol = symbol.upper()
    try:
        report = await _weather_engine.evaluate(symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if explain and _llm_agent:
        report.rationale = await _llm_agent.explain_weather(report)

    await log_weather(report)
    return report


@app.get("/weather/{symbol}/history", tags=["weather"])
async def get_weather_history(symbol: str, limit: int = 20):
    """Return the last N weather reports for *symbol* from the audit log."""
    return await get_recent_weather(symbol.upper(), limit=limit)


class SignalRequest(BaseModel):
    symbol: str
    signal_type: SignalType
    direction: OrderSide
    strength: float = 0.7
    notional_usd: float = 500.0
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    notes: str = ""
    explain: bool = False


@app.post("/signal", tags=["trading"])
async def evaluate_signal(req: SignalRequest, x_trading_token: str = Header(default="")):
    """
    Submit an opportunity signal.  The system will:
      1. Run a fresh weather check.
      2. Fetch current account equity.
      3. Run the deterministic risk engine.
      4. Return the RiskDecision (never places an order automatically).
    """
    if not settings.trading_api_token or not hmac.compare_digest(x_trading_token, settings.trading_api_token):
        raise HTTPException(status_code=401, detail="A valid private dashboard token is required for account-backed risk evaluation.")
    symbol = req.symbol.upper()

    # Build signal
    signal = OpportunitySignal(
        symbol=symbol,
        signal_type=req.signal_type,
        direction=req.direction,
        strength=req.strength,
        notional_usd=req.notional_usd,
        entry_price=req.entry_price,
        stop_price=req.stop_price,
        target_price=req.target_price,
        notes=req.notes,
    )
    await log_signal(signal)

    # Fresh weather
    try:
        report = await _weather_engine.evaluate(symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Weather engine error: {exc}")
    await log_weather(report)

    # Fail closed: never approve a signal using invented account equity.
    # The current API evaluates signals only; it does not submit orders.
    try:
        acc = await _client.get_account_balance()
        if isinstance(acc, dict):
            account_rows = [acc]
        else:
            account_rows = list(acc or [])
        usdt_account = next(
            (row for row in account_rows if str(row.get("marginCoin", "USDT")).upper() == "USDT"),
            account_rows[0] if account_rows else None,
        )
        if not usdt_account:
            raise RuntimeError("Bitget returned no USDT futures account")
        equity_value = usdt_account.get("usdtEquity", usdt_account.get("equity"))
        if equity_value is None or float(equity_value) <= 0:
            raise RuntimeError("Bitget account equity is missing or non-positive")
        equity = float(equity_value)

        positions = await _client.get_positions(symbol=symbol)
        existing_notional = 0.0
        for position in positions or []:
            try:
                existing_notional += abs(float(
                    position.get("total", position.get("size", position.get("available", 0))) or 0
                ) * float(position.get("markPrice", position.get("averageOpenPrice", 0)) or 0))
            except (TypeError, ValueError):
                logger.warning("[api] Could not parse a position while calculating exposure")
    except Exception as exc:
        logger.warning(f"[api] Account/risk context unavailable; rejecting closed: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Risk evaluation unavailable: a valid Bitget account and positions are required.",
        ) from exc

    # Risk decision (deterministic)
    decision = _risk_engine.evaluate(
        signal=signal,
        weather=report,
        account_equity=equity,
        existing_notional=existing_notional,
    )
    await log_decision(decision)

    # LLM rationale
    rationale = ""
    if req.explain and _llm_agent:
        if decision.approved:
            rationale = await _llm_agent.explain_weather(report)
        else:
            rationale = await _llm_agent.explain_rejection(signal, decision)

    return {
        "signal": signal.model_dump(),
        "weather": report.model_dump(),
        "decision": decision.model_dump(),
        "rationale": rationale,
    }


@app.get("/trades", tags=["trading"])
async def list_trades(limit: int = 50):
    return await get_trade_history(limit=limit)


@app.get("/trades/{symbol}", tags=["trading"])
async def list_trades_for_symbol(symbol: str, limit: int = 50):
    return await get_trade_history(symbol=symbol.upper(), limit=limit)


@app.get("/account", tags=["account"])
async def get_account(x_trading_token: str = Header(default="")):
    """Return live account balance and open positions."""
    if not settings.trading_api_token or not hmac.compare_digest(x_trading_token, settings.trading_api_token):
        raise HTTPException(status_code=401, detail="A valid private dashboard token is required to view account data.")
    try:
        balance = await _client.get_account_balance()
        positions = await _client.get_positions()
        return {"balance": balance, "positions": positions}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


class RealityOrderRequest(BaseModel):
    symbol: str
    side: str
    qty: float = Field(gt=0, le=1000000)
    order_type: str = "market"


@app.get("/trading/status", tags=["trading"])
async def trading_status():
    """Describe availability without revealing credentials or tokens."""
    enabled = settings.live_trading_enabled and bool(settings.trading_api_token)
    return {"live_trading_enabled": enabled, "mode": "live" if enabled else "disabled"}


@app.post("/trading/reality-order", tags=["trading"])
async def place_reality_order(req: RealityOrderRequest, x_trading_token: str = Header(default="")):
    """Manually submit one Reality spot order; disabled unless a self-host admin opts in."""
    if not settings.live_trading_enabled or not settings.trading_api_token:
        raise HTTPException(status_code=503, detail="Live trading is disabled by the server administrator.")
    if not hmac.compare_digest(x_trading_token, settings.trading_api_token):
        raise HTTPException(status_code=401, detail="A valid trading access token is required.")
    symbol = req.symbol.strip()
    if not re.fullmatch(r"r[A-Za-z0-9]{1,15}USDT", symbol):
        raise HTTPException(status_code=422, detail="Use a Reality stock symbol such as rAAPLUSDT.")
    side = req.side.lower()
    if side not in {"buy", "sell"}:
        raise HTTPException(status_code=422, detail="side must be buy or sell.")
    order_type = req.order_type.lower()
    if order_type != "market":
        raise HTTPException(status_code=422, detail="Only market orders are currently supported.")
    try:
        return await _client.place_reality_order(symbol, side, str(req.qty), order_type)
    except Exception as exc:
        logger.exception("[api] Reality order submission failed")
        raise HTTPException(status_code=502, detail=f"Bitget rejected or could not confirm the order: {exc}") from exc


# ---------------------------------------------------------------------------
# WebSocket — streaming weather
# ---------------------------------------------------------------------------


@app.websocket("/ws/weather/{symbol}")
async def ws_weather(websocket: WebSocket, symbol: str):
    """
    Streams Liquidity Weather updates every `interval` seconds.
    Client can send JSON `{"interval": 60}` to change the poll rate.
    """
    await websocket.accept()
    symbol = symbol.upper()
    interval = settings.weather_poll_seconds
    logger.info(f"[ws] Client connected for {symbol}")

    try:
        while True:
            try:
                report = await _weather_engine.evaluate(symbol)
                await log_weather(report)
                await websocket.send_text(report.model_dump_json())
            except Exception as exc:
                await websocket.send_text(
                    json.dumps({"error": str(exc), "symbol": symbol})
                )
            # Check for client message (non-blocking)
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                msg = json.loads(raw)
                if "interval" in msg:
                    interval = max(5, int(msg["interval"]))
            except (asyncio.TimeoutError, json.JSONDecodeError):
                pass

            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        logger.info(f"[ws] Client disconnected for {symbol}")
