# 🌙 NOCTURNE — Liquidity Weather Agent for 24/7 Tokenized U.S. Stocks

> **Base Camp Hackathon S2 — Bitget Agent Hub Track**  
> *"In tokenized equities, the highest-value agent action is often not to trade."*

[![Tests](https://img.shields.io/badge/tests-11%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal.svg)]()
[![MCP](https://img.shields.io/badge/MCP-JSON--RPC%20stdio-purple.svg)]()

---

## 🎯 Executive Summary & Thesis

Tokenized U.S. stocks trade round-the-clock on exchanges like Bitget, offering retail traders continuous access to equity markets. However, round-the-clock accessibility creates a severe, underappreciated structural trap:

> **Recent IMF research found that over 50% of tokenized-stock volume takes place outside regular U.S. trading hours, where tokenized shares exhibit ~1.5x higher volatility and significantly shallower order-book depth.** Over 85% of overnight moves are absorbed within 5 minutes of regular market open.

Most autonomous trading bots blindly execute whenever a signal appears, suffering extreme slippage, wide bid-ask spreads, and false breakouts.

**NOCTURNE** challenges this assumption. Instead of a sentiment bot that gambles on after-hours headlines, NOCTURNE is an **execution-risk and liquidity-regime gatekeeper**. It evaluates whether the market environment is structurally safe to trade before any order is submitted.

## Current dashboard and live trading setup

The dashboard's stock search loads the current Bitget Reality instrument catalog through `GET /symbols`. AI rationale starts **off**; enabling the AI switch requests one explanation per weather refresh, including each 30-second refresh when Live monitoring is enabled. Ordinary weather checks do not call the language model.

Reality spot orders are manual and disabled by default. The dashboard/backend use `LIVE_TRADING_ENABLED=true`, a strong private `TRADING_API_TOKEN`, and the operator's own Bitget UTA API credentials to enable order submission. Keep those settings on a private, self-hosted installation only. The shared Render deployment keeps live trading off; never put personal exchange keys on a public service. Private account reads and account-backed signal evaluation require the operator-only token. `POST /trading/reality-order` accepts market buy/sell requests and requires the `X-Trading-Token` header. Market-buy quantity is quote USDT; market-sell quantity is base shares. Orders are real when enabled; the endpoint does not paper trade.

---

## 🏛️ System Architecture

```
                                 ┌──────────────────────────────┐
                                 │      Bitget Agent Hub        │
                                 │   Market Data / Order APIs   │
                                 └──────────────┬───────────────┘
                                                │
                                                ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │                               NOCTURNE CORE                                 │
  │                                                                             │
  │  ┌──────────────────────────┐             ┌──────────────────────────────┐  │
  │  │   Layer 1: Opportunity   │             │   Layer 2: Execution Gate    │  │
  │  │         Detector         │             │                              │  │
  │  │  - Earnings Dislocation  │             │  [Liquidity Weather Engine]  │  │
  │  │  - Macro Shock Response  │──Signal────►│   Spread (30%) Depth (25%)   │  │
  │  │  - Cross-Asset Divergence│             │   Vol (25%) Lead/Lag (10%)   │  │
  │  │  - Mean Reversion Bands  │             │   Event Risk (10%)           │  │
  │  └──────────────────────────┘             └──────────────┬───────────────┘  │
  │                                                          │                  │
  │                                                          ▼                  │
  │                                           ┌──────────────────────────────┐  │
  │                                           │  Deterministic Risk Engine   │  │
  │                                           │  (8 sequential hard checks)  │  │
  │                                           │  *LLM NEVER controls orders* │  │
  │                                           └──────────────┬───────────────┘  │
  │                                                          │                  │
  │         ┌───────────────────────┐                        ▼                  │
  │         │   LLM Rationale Agent │◄──Regime / Reason──Decision               │
  │         │ (Plain-English only)  │             [APPROVED / REJECTED]         │
  │         └───────────────────────┘                        │                  │
  │                                                          ▼                  │
  │                                           ┌──────────────────────────────┐  │
  │                                           │  Append-Only Audit Log (DB)  │  │
  └───────────────────────────────────────────┴──────────────┬──────────────────┘
                                                             │
                  ┌──────────────────────────────────────────┼───────────────────────┐
                  ▼                                          ▼                       ▼
      ┌───────────────────────┐                  ┌──────────────────────┐  ┌──────────────────┐
      │   FastAPI + WebSockets│                  │  Model Context (MCP) │  │ Premium UI Glass │
      │   (REST Endpoints)    │                  │  Server for AI Agents│  │ Dashboard        │
      └───────────────────────┘                  └──────────────────────┘  └──────────────────┘
```

---

## 🌦️ The Liquidity Weather Score

NOCTURNE computes a composite score ($0–100$) across 5 normalized dimensions:

$$\text{Weather Score} = 0.30 \cdot S_{\text{spread}} + 0.25 \cdot S_{\text{depth}} + 0.25 \cdot S_{\text{volatility}} + 0.10 \cdot S_{\text{leadlag}} + 0.10 \cdot S_{\text{event}}$$

| State | Score Range | Meaning | Permitted Agent Action |
|:---:|:---:|:---|:---|
| **`CLEAR`** | $\ge 70.0$ | Liquid, normal spreads, deep book | **Full strategy size (100%)** |
| **`CLOUDY`** | $45.0 – 69.9$ | Tradable but elevated volatility or wider spread | **Half size (50%) + tight stop** |
| **`STORM`** | $20.0 – 44.9$ | Shallow depth, wide spreads, shock regime | **No new entries; hold/manage only** |
| **`BLACKOUT`** | $< 20.0$ | Extreme spread, data gap, halt, or risk breach | **Cancel pending & stand down** |

---

## 🛡️ Deterministic Risk Gatekeeper (8 Sequential Hard Checks)

1. **Weather Gate**: Rejects orders immediately during `STORM` or `BLACKOUT`.
2. **Spread Gate**: Bid-ask spread score must exceed minimum liquidity threshold.
3. **Depth Gate**: Order book depth within $\pm 25$ bps must support proposed notional.
4. **Volatility Gate**: Realized volatility must be within acceptable strategy limits.
5. **Per-Trade Risk Cap**: Dollar risk capped at $\le 0.5\%$ of account equity.
6. **Position-Size Cap**: Total exposure per asset capped at $\le 5\%$ of equity.
7. **Daily-Loss Gate**: Realized daily loss capped at $2\%$ of equity.
8. **Consecutive-Loss Gate**: 3 consecutive losses trigger an automatic trading cooldown.

---

## 📊 Backtest & Empirical Validation Evidence

Tested across a **90-day simulation of 24/7 tokenized U.S. stocks (hourly bars)** incorporating IMF-documented overnight microstructure realities (elevated off-hours volatility, wide overnight spreads, thin order books, and adverse toxic flow during dislocations):

| Metric | Signal-Only Agent (Ungated) | NOCTURNE Agent (Liquidity-Gated) | Buy & Hold Benchmark | Status |
|:---|---:|---:|---:|:---:|
| **Net Total Return** | **-12.57%** | **+1.59%** | +32.89% | **Observed** |
| **Sharpe Ratio** | -5.64 | **+3.63** | +2.11 | **Observed** |
| **Sortino Ratio** | -5.63 | **+9.10** | +2.22 | **Observed** |
| **Max Drawdown** | 12.79% | **0.29%** | 23.93% | **Observed** |
| **Win Rate** | 34.1% | **57.6%** | 100.0% | **Observed** |
| **Avg Realized Slippage** | **15.0 bps** | **3.0 bps** | 3.0 bps | **Observed** |
| **Turnover Ratio** | 17.8x | 7.8x | 1.0x | **Observed** |
| **Blocked Toxic Trades** | 0 (0.0%) | **168 (44.4%)** | N/A | **Observed** |

### Key Validation Finding
> In shallow overnight markets, blind execution turns winning trade ideas into losing trades due to adverse selection and 15+ bps slippage. NOCTURNE blocked **168 toxic overnight trades (44.4% of all signals)**, slashing maximum drawdown from **12.79% to 0.29%** and lifting net Sharpe from **-5.64 to +3.63**.

---

## 🚀 Quickstart & Usage

### 1. Run the Demo Weather Evaluation
Evaluates live Bitget market ticker and checks risk rules:
```powershell
python main.py --demo
```

### 2. Run the 90-Day Backtest & Validation Engine
Simulates 90 days of 24/7 tokenized equity market data and exports `backtest_results.json`:
```powershell
python main.py --backtest
```

### 3. Start the FastAPI REST & WebSocket Backend
```powershell
python main.py --port 8000
```
Open interactive Swagger docs at `http://localhost:8000/docs`.

### 4. Open the Real-Time Glassmorphic Dashboard
Open `dashboard/index.html` in your browser. It visualizes:
- Live 5-component animated score ring
- Dynamic CLEAR / CLOUDY / STORM / BLACKOUT status badge
- Historical weather chart
- Interactive Signal Lab to test proposed trades against the risk engine
- Audit log & trade history

### 5. Run the Model Context Protocol (MCP) Server
Allows any AI coding assistant or agent runtime (Claude Desktop, Cursor, Codex, Antigravity) to query NOCTURNE:
```powershell
python main.py --mcp
```

### 6. Run the Test Suite
```powershell
python -m pytest -v
```
All 11 unit and integration tests pass verifying the risk engine, weather scores, API endpoints, and backtesting.

---

## 🤖 MCP Tool Interface

When configured with Bitget Agent Hub or MCP-enabled tools, agents can call:
- `get_liquidity_weather(symbol)` — Evaluates current weather score, breakdown, and regime.
- `evaluate_order_risk(symbol, signal_type, direction, notional_usd, account_equity)` — Tests a proposed order through the 8 deterministic risk checks.
- `get_market_regime(symbol)` — Quick check of state and permitted position size percentage.
- `list_supported_symbols()` — Enumerates monitored tokenized stock perpetuals.
- `get_backtest_metrics()` — Returns quantitative validation evidence for audit.

---

## 📜 License & Disclaimer

MIT License. NOCTURNE is a quantitative research and execution-risk management framework designed for the Bitget Agent Hub hackathon.
