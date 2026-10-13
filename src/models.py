"""NOCTURNE — Core domain models and enums."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WeatherState(str, Enum):
    """Four-state Liquidity Weather output."""
    CLEAR = "CLEAR"       # Liquid, stable, normal spreads → full strategy size
    CLOUDY = "CLOUDY"     # Tradeable but elevated risk → reduced size, tighter stops
    STORM = "STORM"       # Poor liquidity or unstable pricing → no new entries
    BLACKOUT = "BLACKOUT" # Data gap, extreme spread, halt, or risk-limit breach → stand down


class AgentAction(str, Enum):
    """Agent action recommendations."""
    TRADE = "TRADE"
    REDUCE = "REDUCE"
    WAIT = "WAIT"
    STAND_DOWN = "STAND_DOWN"


class SignalType(str, Enum):
    """Opportunity detector signal types."""
    EARNINGS_DISLOCATION = "EARNINGS_DISLOCATION"
    MACRO_SHOCK = "MACRO_SHOCK"
    CROSS_MARKET_DIVERGENCE = "CROSS_MARKET_DIVERGENCE"
    MEAN_REVERSION = "MEAN_REVERSION"


class OrderSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class OrderStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Component Scores
# ---------------------------------------------------------------------------


class ComponentScores(BaseModel):
    """Individual scores (0-100) for each Liquidity Weather component."""
    spread_score: float = Field(ge=0, le=100, description="Bid-ask spread vs recent normal")
    depth_score: float = Field(ge=0, le=100, description="Order-book depth vs normal")
    volatility_score: float = Field(ge=0, le=100, description="Realized vol vs baseline")
    lead_lag_score: float = Field(ge=0, le=100, description="Tokenized vs underlying consistency")
    event_score: float = Field(ge=0, le=100, description="Absence of event risk")


# ---------------------------------------------------------------------------
# Liquidity Weather Report
# ---------------------------------------------------------------------------


class LiquidityWeatherReport(BaseModel):
    """Full weather report for a symbol at a point in time."""
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Scores
    scores: ComponentScores
    composite_score: float = Field(ge=0, le=100)

    # State & recommendation
    state: WeatherState
    action: AgentAction
    recommended_size_pct: float = Field(
        ge=0, le=1.0,
        description="Fraction of normal position size that is allowed",
    )

    # Raw market data snapshot
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    spread_bps: Optional[float] = None
    depth_within_25bps: Optional[float] = None  # USDT notional
    realized_vol_1h: Optional[float] = None     # annualised %
    vol_baseline: Optional[float] = None

    # Human-readable rationale (filled by LLM)
    rationale: str = ""
    data_quality_ok: bool = True


# ---------------------------------------------------------------------------
# Opportunity Signal
# ---------------------------------------------------------------------------


class OpportunitySignal(BaseModel):
    """Output of the Layer-1 opportunity detector."""
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    signal_type: SignalType
    direction: OrderSide
    strength: float = Field(ge=0, le=1.0, description="Normalised signal strength 0-1")
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    notional_usd: float = Field(gt=0)
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    invalidation_condition: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Risk-Engine Decision
# ---------------------------------------------------------------------------


class RiskDecision(BaseModel):
    """Deterministic risk engine verdict on a proposed order."""
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    symbol: str
    approved: bool
    rejection_reasons: list[str] = Field(default_factory=list)

    # Approved parameters (may be reduced from signal)
    approved_notional_usd: Optional[float] = None
    approved_size_pct: Optional[float] = None
    stop_price: Optional[float] = None

    weather_state: WeatherState
    weather_score: float
    decided_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Trade Record
# ---------------------------------------------------------------------------


class TradeRecord(BaseModel):
    """Full lifecycle record of a trade."""
    trade_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    decision_id: str
    symbol: str
    side: OrderSide
    status: OrderStatus = OrderStatus.PENDING

    # Execution
    requested_notional: float
    approved_notional: Optional[float] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    slippage_bps: Optional[float] = None

    # Context
    weather_state_at_entry: Optional[WeatherState] = None
    weather_score_at_entry: Optional[float] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    bitget_order_id: Optional[str] = None
    notes: str = ""
