# NOCTURNE — Liquidity-Weather Agent for 24/7 Tokenized U.S. Stocks

## One-line pitch

**NOCTURNE is an execution-risk-aware AI agent that treats tokenized U.S. stocks like a changing weather system: it does not blindly trade 24/7—it decides whether the market is safe enough to trade, wait, reduce exposure, or stand down.**

Most “24/7 trading agent” ideas assume that because a market is open, it is tradable. NOCTURNE challenges that assumption. Tokenized equities often trade outside regular U.S. hours, but liquidity can be thin, spreads can widen, and volatility can be materially higher than the underlying stock. Recent IMF research found that more than half of tokenized-equity trading occurs outside traditional market hours, while tokenized shares were about 1.5x as volatile and significantly less liquid than conventional equities. It also found that once U.S. markets opened, more than 85% of overnight movement in tokenized shares was reflected in traditional shares within five minutes. That creates a specific, measurable problem: **overnight price movement is real, but the cost and risk of acting on it can overwhelm the opportunity.**

NOCTURNE is therefore not another “sentiment bot” or generic momentum agent. It is a **liquidity-and-regime gatekeeper** that decides when an autonomous agent should be allowed to act.

## Why this is different

| Usual hackathon idea | NOCTURNE approach |
|---|---|
| “AI reads news and buys/sells stocks” | AI evaluates whether the current market regime is executable at all |
| Trades whenever a signal appears | Requires signal strength **and** acceptable liquidity, spread, depth, and volatility |
| Treats 24/7 access as an advantage | Treats 24/7 access as a conditional advantage |
| Uses an LLM to choose trades | Uses an LLM to explain regime changes, while deterministic rules control risk |
| Optimizes only returns | Optimizes risk-adjusted net execution quality |
| One agent does everything | Separate research, risk, execution, and audit roles |

The novel thesis is:

> **In tokenized U.S. stocks, the highest-value agent action is often not to trade. NOCTURNE learns when the overnight market is structurally unsafe—wide spreads, shallow depth, unstable prices, or event risk—and prevents the agent from turning a valid idea into a bad execution.**

## Target user

**Primary user:** Active retail traders on Bitget with approximately **$1,000–$25,000** in trading capital, medium-to-high risk tolerance, who trade tokenized U.S. stocks or stock perpetuals **2–10 times per week** and want exposure to overnight/weekend moves without babysitting charts.

**Specific use case:** A trader sees a major after-hours earnings move or macro headline. They want to participate, but they do not know whether the tokenized market currently has enough liquidity and reasonable spreads to enter safely. NOCTURNE gives them a clear decision:

- `TRADE`: conditions are acceptable.
- `REDUCE`: trade only at a smaller size.
- `WAIT`: setup is valid but execution conditions are poor.
- `STAND DOWN`: market is unstable, illiquid, or risk limits are breached.

This is deliberately narrower than “all traders.” It targets people who already understand trading risk but need discipline around off-hours execution.

## Core product value

NOCTURNE turns a chaotic 24/7 market into a simple, explainable **Liquidity Weather Score**:

\[
\text{Liquidity Weather Score} =
w_1S_{\text{spread}} +
w_2S_{\text{depth}} +
w_3S_{\text{volatility}} +
w_4S_{\text{leadlag}} +
w_5S_{\text{event}}
\]

Where each component is normalized from 0 to 100:

- **Spread score:** current bid-ask spread versus its recent normal range.
- **Depth score:** available liquidity within a defined price distance from mid-price.
- **Volatility score:** short-horizon realized volatility versus baseline.
- **Lead-lag score:** consistency between tokenized-stock movement and the underlying stock or related market signal.
- **Event score:** scheduled earnings, macro releases, halts, or abnormal news intensity.

The agent outputs one of four states:

| State | Meaning | Agent behavior |
|---|---|---|
| `CLEAR` | Liquid, stable, normal spreads | Full strategy size allowed |
| `CLOUDY` | Tradeable but elevated risk | Reduced size and tighter stops |
| `STORM` | Poor liquidity or unstable pricing | No new entries; manage existing risk |
| `BLACKOUT` | Data gap, extreme spread, halt, or risk-limit breach | Cancel pending orders and stand down |

## Strategy logic

NOCTURNE uses a two-layer design.

### Layer 1: Opportunity detector

It looks for a limited set of high-signal overnight events:

1. **After-hours earnings dislocation:** tokenized stock moves sharply after an earnings release.
2. **Macro shock response:** CPI, Fed decision, employment data, or geopolitical headline moves the tokenized market.
3. **Cross-market divergence:** tokenized stock diverges from a correlated reference asset or index proxy.
4. **Liquidity-driven mean reversion:** price moves beyond a volatility-adjusted band while spread and depth remain acceptable.

The agent does **not** use all signals simultaneously. Each signal has its own entry condition, invalidation condition, and risk budget.

### Layer 2: Execution gatekeeper

Before any order is considered, NOCTURNE checks:

- Spread is below a symbol-specific maximum.
- Order-book depth can support the intended notional size.
- Realized volatility is below the strategy’s maximum.
- The tokenized asset is not in an abnormal data gap.
- No earnings, halt, or macro event is inside a blocked time window.
- Daily loss, position size, and consecutive-loss limits have not been hit.
- The proposed order passes a pre-trade risk simulation.

Only if both layers pass does the agent request execution through Bitget Agent Hub.

## Why judges should care

This idea directly matches the hackathon’s core theme: tokenized U.S. stocks make 24/7 trading possible, but they also create a new execution-risk problem. Bitget Agent Hub provides market, account, and trading data across crypto, U.S. stocks, and other assets, plus MCP, CLI, and trading skills for checking prices, placing and cancelling orders, and managing positions. NOCTURNE uses that infrastructure not merely to automate trades, but to make autonomous trading safer.

The project is credible because it has a clear failure mode to solve: **a good signal can still be a bad trade when liquidity is poor.** That is a real, measurable problem rather than a vague “AI improves trading” claim.

## Demo experience

A user opens the NOCTURNE dashboard and asks:

> “Is AAPL safe to trade right now?”

NOCTURNE replies:

> **Liquidity Weather: STORM**  
> Spread is 3.8x its 30-day overnight median. Order-book depth within 0.25% of mid is 62% below normal. Short-horizon volatility is elevated after an earnings release.  
>   
> **Recommendation:** Do not open a new position. If already long, reduce exposure by 40% or set a hard stop.  
>   
> **Why:** The setup may be directionally valid, but expected slippage and adverse selection outweigh the current edge.

The user can then ask:

> “Show me the last time conditions were CLEAR.”

The dashboard shows a timeline of regime states, spread, depth, volatility, and the agent’s decisions.

## Validation plan

### Backtest

Use at least 60–90 days of hourly or 15-minute data for 10–20 liquid tokenized U.S. stocks.

Compare three versions:

1. **Signal-only agent:** trades whenever the opportunity detector fires.
2. **NOCTURNE agent:** trades only when the Liquidity Weather Score passes.
3. **Buy-and-hold benchmark:** passive exposure to the same universe.

Measure:

- Net return after fees and estimated slippage.
- Sharpe ratio.
- Sortino ratio.
- Maximum drawdown.
- Win rate.
- Trade count.
- Average realized slippage.
- Turnover.
- Percentage of signals correctly blocked during poor-liquidity periods.

### Success thresholds

These are **targeted** until measured:

- Net return improves versus signal-only agent.
- Maximum drawdown is at least 20% lower.
- Sharpe ratio is at least 1.0 after costs.
- At least 30 completed paper trades.
- Average slippage is reduced versus signal-only execution.
- No single trade risks more than 0.5% of account equity.

### Product validation

Run a closed beta with 10–20 Bitget traders.

Track:

- Activation: user connects Agent Hub and completes first Liquidity Weather check.
- Task completion: user receives a usable trade/wait/stand-down recommendation.
- Retention: user returns within 7 days.
- Decision influence: user follows or explicitly overrides the recommendation.
- Risk: percentage of recommendations that would have breached user-defined limits.

## Bitget integration

NOCTURNE should use:

- **Bitget Agent Hub** for agentic account access, market data, account data, and trading actions.
- **Bitget MCP Server** for natural-language agent integration in Claude, Cursor, Codex, or a custom agent runtime.
- **Bitget REST/WebSocket APIs** for prices, order books, positions, balances, and order management.
- **Bitget Playbook** for backtesting, deployment, and monitoring where supported.
- **Bitget Unified Trading Account** concepts for cross-asset exposure awareness.

The agent should be built with a strict separation:

- LLM: interprets context, explains regime changes, generates human-readable rationales.
- Deterministic risk engine: decides whether an order is permitted.
- Execution service: submits orders only after risk approval.
- Audit log: records every signal, decision, rejection, and order.

## Non-goals

NOCTURNE does **not**:

- Promise profits.
- Use unlimited leverage.
- Trade without explicit user risk limits.
- Let the LLM directly place orders.
- Operate as financial advice.
- Trade during unresolved data outages or extreme spreads.

## What makes it win

1. It solves a real, current problem in tokenized-stock trading.
2. It is not a generic ChatGPT trading bot.
3. It has a measurable hypothesis and clear metrics.
4. It uses Bitget Agent Hub meaningfully.
5. It emphasizes safety, explainability, and execution quality.
6. It can be demoed with a simple dashboard and a live/paper agent.

## Future roadmap

- Add per-symbol liquidity profiles.
- Add reinforcement learning for dynamic position sizing.
- Add portfolio-level weather scoring.
- Add alerts for liquidity deterioration before entry.
- Add social/community strategy templates.
- Add broker-agnostic execution adapters.
- Add a public “Liquidity Weather Index” for tokenized stocks.

## License

MIT License.

## Disclaimer

NOCTURNE is a research and risk-management tool. It is not financial advice, does not guarantee profit, and may lose money. Users must configure their own risk limits and understand that tokenized stocks can be volatile and illiquid.
