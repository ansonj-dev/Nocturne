"""NOCTURNE — Audit Log (append-only SQLite via SQLAlchemy async).

Every signal, decision, weather report, and order event is recorded here.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from .config import settings
from .models import LiquidityWeatherReport, OpportunitySignal, RiskDecision, TradeRecord

# Ensure aiosqlite driver is used for SQLite URL
_db_url = settings.database_url
if _db_url.startswith("sqlite://") and not _db_url.startswith("sqlite+aiosqlite://"):
    _db_url = "sqlite+aiosqlite://" + _db_url[len("sqlite://"):]

_engine = create_async_engine(
    _db_url,
    echo=False,
    future=True,
)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS weather_reports (
    id          TEXT PRIMARY KEY,
    symbol      TEXT NOT NULL,
    ts          TEXT NOT NULL,
    state       TEXT NOT NULL,
    action      TEXT NOT NULL,
    score       REAL NOT NULL,
    scores_json TEXT NOT NULL,
    rationale   TEXT,
    raw_json    TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id          TEXT PRIMARY KEY,
    symbol      TEXT NOT NULL,
    type        TEXT NOT NULL,
    direction   TEXT NOT NULL,
    strength    REAL NOT NULL,
    notional    REAL NOT NULL,
    ts          TEXT NOT NULL,
    raw_json    TEXT
);

CREATE TABLE IF NOT EXISTS risk_decisions (
    id              TEXT PRIMARY KEY,
    signal_id       TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    approved        INTEGER NOT NULL,
    reasons_json    TEXT,
    weather_state   TEXT,
    weather_score   REAL,
    approved_notional REAL,
    ts              TEXT NOT NULL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS trade_records (
    id              TEXT PRIMARY KEY,
    signal_id       TEXT NOT NULL,
    decision_id     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    status          TEXT NOT NULL,
    requested_notional REAL,
    approved_notional  REAL,
    entry_price     REAL,
    exit_price      REAL,
    realized_pnl    REAL,
    slippage_bps    REAL,
    weather_state   TEXT,
    weather_score   REAL,
    created_at      TEXT NOT NULL,
    raw_json        TEXT
);
"""


async def init_db() -> None:
    """Create tables if they don't exist."""
    async with _engine.begin() as conn:
        for stmt in _DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))
    logger.info("[audit] Database initialised")


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

async def log_weather(report: LiquidityWeatherReport) -> None:
    async with _SessionLocal() as session:
        await session.execute(
            text("""
            INSERT OR REPLACE INTO weather_reports
              (id, symbol, ts, state, action, score, scores_json, rationale, raw_json)
            VALUES (:id, :symbol, :ts, :state, :action, :score, :scores_json, :rationale, :raw_json)
            """),
            {
                "id": report.report_id,
                "symbol": report.symbol,
                "ts": report.timestamp.isoformat(),
                "state": report.state.value,
                "action": report.action.value,
                "score": report.composite_score,
                "scores_json": report.scores.model_dump_json(),
                "rationale": report.rationale,
                "raw_json": report.model_dump_json(),
            },
        )
        await session.commit()


async def log_signal(signal: OpportunitySignal) -> None:
    async with _SessionLocal() as session:
        await session.execute(
            text("""
            INSERT OR REPLACE INTO signals
              (id, symbol, type, direction, strength, notional, ts, raw_json)
            VALUES (:id, :symbol, :type, :direction, :strength, :notional, :ts, :raw_json)
            """),
            {
                "id": signal.signal_id,
                "symbol": signal.symbol,
                "type": signal.signal_type.value,
                "direction": signal.direction.value,
                "strength": signal.strength,
                "notional": signal.notional_usd,
                "ts": signal.detected_at.isoformat(),
                "raw_json": signal.model_dump_json(),
            },
        )
        await session.commit()


async def log_decision(decision: RiskDecision) -> None:
    async with _SessionLocal() as session:
        await session.execute(
            text("""
            INSERT OR REPLACE INTO risk_decisions
              (id, signal_id, symbol, approved, reasons_json, weather_state,
               weather_score, approved_notional, ts, raw_json)
            VALUES (:id, :signal_id, :symbol, :approved, :reasons_json,
                    :weather_state, :weather_score, :approved_notional, :ts, :raw_json)
            """),
            {
                "id": decision.decision_id,
                "signal_id": decision.signal_id,
                "symbol": decision.symbol,
                "approved": int(decision.approved),
                "reasons_json": json.dumps(decision.rejection_reasons),
                "weather_state": decision.weather_state.value,
                "weather_score": decision.weather_score,
                "approved_notional": decision.approved_notional_usd,
                "ts": decision.decided_at.isoformat(),
                "raw_json": decision.model_dump_json(),
            },
        )
        await session.commit()


async def log_trade(trade: TradeRecord) -> None:
    async with _SessionLocal() as session:
        await session.execute(
            text("""
            INSERT OR REPLACE INTO trade_records
              (id, signal_id, decision_id, symbol, side, status,
               requested_notional, approved_notional, entry_price, exit_price,
               realized_pnl, slippage_bps, weather_state, weather_score,
               created_at, raw_json)
            VALUES (:id, :signal_id, :decision_id, :symbol, :side, :status,
                    :requested_notional, :approved_notional, :entry_price, :exit_price,
                    :realized_pnl, :slippage_bps, :weather_state, :weather_score,
                    :created_at, :raw_json)
            """),
            {
                "id": trade.trade_id,
                "signal_id": trade.signal_id,
                "decision_id": trade.decision_id,
                "symbol": trade.symbol,
                "side": trade.side.value,
                "status": trade.status.value,
                "requested_notional": trade.requested_notional,
                "approved_notional": trade.approved_notional,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "realized_pnl": trade.realized_pnl,
                "slippage_bps": trade.slippage_bps,
                "weather_state": trade.weather_state_at_entry.value if trade.weather_state_at_entry else None,
                "weather_score": trade.weather_score_at_entry,
                "created_at": trade.created_at.isoformat(),
                "raw_json": trade.model_dump_json(),
            },
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

async def get_recent_weather(symbol: str, limit: int = 20) -> list[dict]:
    async with _SessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT raw_json FROM weather_reports "
                "WHERE symbol=:symbol ORDER BY ts DESC LIMIT :limit"
            ),
            {"symbol": symbol, "limit": limit},
        )
        return [json.loads(row[0]) for row in result.fetchall()]


async def get_trade_history(symbol: Optional[str] = None, limit: int = 50) -> list[dict]:
    async with _SessionLocal() as session:
        if symbol:
            result = await session.execute(
                text(
                    "SELECT raw_json FROM trade_records "
                    "WHERE symbol=:symbol ORDER BY created_at DESC LIMIT :limit"
                ),
                {"symbol": symbol, "limit": limit},
            )
        else:
            result = await session.execute(
                text(
                    "SELECT raw_json FROM trade_records "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {"limit": limit},
            )
        return [json.loads(row[0]) for row in result.fetchall()]
