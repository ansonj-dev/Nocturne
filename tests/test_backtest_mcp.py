"""Unit and integration tests for Backtest and MCP Server."""
import pytest
import asyncio
from src.backtest import BacktestEngine, TokenizedStockDataGenerator
from src.mcp_server import NocturneMCPServer


def test_backtest_execution():
    """Verify backtester generates market data and computes metrics for 3 strategies."""
    df = TokenizedStockDataGenerator.generate_market_data(days=15, freq_minutes=60, seed=123)
    assert len(df) == 15 * 24
    assert "weather_score" in df.columns
    assert "weather_state" in df.columns

    engine = BacktestEngine(initial_capital=5000.0)
    results = engine.run_all(df, symbol="AAPLUSDT")

    assert "signal_only" in results
    assert "nocturne" in results
    assert "buy_and_hold" in results

    noc = results["nocturne"]
    assert noc.strategy_name == "NOCTURNE Agent (Liquidity-Gated)"
    assert noc.trade_count >= 0
    assert noc.avg_slippage_bps <= results["signal_only"].avg_slippage_bps


@pytest.mark.asyncio
async def test_mcp_server_tools():
    """Verify MCP server tool handling."""
    server = NocturneMCPServer()

    # Tool: list_supported_symbols
    syms = await server.handle_tool_call("list_supported_symbols", {})
    assert "symbols" in syms
    assert len(syms["symbols"]) > 0

    # Tool: evaluate_order_risk
    eval_res = await server.handle_tool_call(
        "evaluate_order_risk",
        {
            "symbol": "AAPLUSDT",
            "signal_type": "MEAN_REVERSION",
            "direction": "long",
            "notional_usd": 150.0,
            "account_equity": 5000.0,
        },
    )
    assert "approved" in eval_res
    assert "weather_state" in eval_res
