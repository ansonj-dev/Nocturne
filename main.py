"""NOCTURNE — Application entry point.

Usage:
  python main.py               # start API server (default: port 8000)
  python main.py --port 8080
  python main.py --demo        # run a quick demo weather check (no server)
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger


def main() -> None:
    parser = argparse.ArgumentParser(description="NOCTURNE Liquidity-Weather Agent")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev mode)")
    parser.add_argument("--demo", action="store_true", help="Run a quick weather demo and exit")
    parser.add_argument("--backtest", action="store_true", help="Run 90-day institutional validation backtest")
    parser.add_argument("--mcp", action="store_true", help="Start the Model Context Protocol (MCP) server on stdio")
    args = parser.parse_args()

    if args.demo:
        asyncio.run(_demo())
        return

    if args.backtest:
        from src.backtest import run_benchmark
        run_benchmark(symbol="AAPLUSDT", days=90)
        return

    if args.mcp:
        from src.mcp_server import NocturneMCPServer
        server = NocturneMCPServer()
        asyncio.run(server.run_stdio())
        return

    import uvicorn
    logger.info(f"Starting NOCTURNE on {args.host}:{args.port}")
    uvicorn.run(
        "src.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


async def _demo() -> None:
    """Quick sanity check — evaluates AAPL weather without a real API key."""
    from src.bitget_client import BitgetClient
    from src.weather_engine import LiquidityWeatherEngine
    from src.risk_engine import RiskEngine
    from src.models import OpportunitySignal, SignalType, OrderSide
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()
    console.print(Panel.fit("[bold cyan]NOCTURNE[/] — Demo Weather Check", border_style="cyan"))

    symbol = "AAPLUSDT"
    console.print(f"\nEvaluating [bold]{symbol}[/]…")

    async with BitgetClient(sandbox=True) as client:
        engine = LiquidityWeatherEngine(client)
        try:
            report = await engine.evaluate(symbol)
        except Exception as exc:
            console.print(f"[red]Weather engine error:[/] {exc}")
            console.print("[dim]Note: Bitget API keys are not configured — this is expected in demo mode.[/]")
            # Show a synthetic demo report
            from src.models import WeatherState, AgentAction, ComponentScores, LiquidityWeatherReport
            from datetime import datetime
            report = LiquidityWeatherReport(
                symbol=symbol,
                scores=ComponentScores(spread_score=82, depth_score=74, volatility_score=65, lead_lag_score=70, event_score=80),
                composite_score=74.7,
                state=WeatherState.CLEAR,
                action=AgentAction.TRADE,
                recommended_size_pct=1.0,
                bid=189.20, ask=189.25, mid=189.225, spread_bps=2.6,
                depth_within_25bps=125_000,
                realized_vol_1h=38.2,
                rationale=(
                    "Liquidity Weather: CLEAR (score 74.7/100). "
                    "Spread is at its 30-day median. Order-book depth is healthy. "
                    "Volatility is slightly elevated but within the acceptable range. "
                    "Full strategy size is permitted."
                ),
            )

    # Render report
    state_colour = {"CLEAR": "cyan", "CLOUDY": "yellow", "STORM": "dark_orange", "BLACKOUT": "red"}.get(report.state.value, "white")
    console.print(f"\n[{state_colour}]Weather: {report.state.value}[/]  Score: [bold]{report.composite_score:.1f}/100[/]")
    console.print(f"Action:  [bold]{report.action.value}[/]  Allowed size: {report.recommended_size_pct*100:.0f}%")

    t = Table(show_header=True, header_style="dim")
    t.add_column("Component", style="dim")
    t.add_column("Score", justify="right")
    s = report.scores
    t.add_row("Spread",     str(round(s.spread_score)))
    t.add_row("Depth",      str(round(s.depth_score)))
    t.add_row("Volatility", str(round(s.volatility_score)))
    t.add_row("Lead-Lag",   str(round(s.lead_lag_score)))
    t.add_row("Event Risk", str(round(s.event_score)))
    console.print(t)

    console.print(f"\n[italic]{report.rationale}[/]")

    # Risk check on a demo signal
    risk = RiskEngine()
    signal = OpportunitySignal(
        symbol=symbol,
        signal_type=SignalType.EARNINGS_DISLOCATION,
        direction=OrderSide.LONG,
        strength=0.75,
        notional_usd=500.0,
        entry_price=report.mid or 189.22,
        stop_price=(report.mid or 189.22) * 0.99,
    )
    decision = risk.evaluate(signal=signal, weather=report, account_equity=5000.0)
    console.print(f"\nRisk Engine: {'[green]APPROVED[/]' if decision.approved else '[red]REJECTED[/]'}")
    if not decision.approved:
        for r in decision.rejection_reasons:
            console.print(f"  • {r}")

    console.print("\n[dim]Open the dashboard at:[/] file://dashboard/index.html")
    console.print("[dim]Start the server with:[/]  python main.py")


if __name__ == "__main__":
    main()
