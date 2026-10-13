"""NOCTURNE — Bitget market-data and trading client wrapper."""
from __future__ import annotations

import time
import hmac
import base64
import hashlib
from typing import Any, Optional
from datetime import datetime, timezone

import httpx
from loguru import logger

from .config import settings


BASE_URL_LIVE = "https://api.bitget.com"
BASE_URL_SANDBOX = "https://api.bitget.com"  # Bitget uses same base; sandbox via demo account


class BitgetClient:
    """
    Thin async wrapper around the Bitget REST API.
    Exposes the data surfaces NOCTURNE needs:
      - Order-book snapshots (depth)
      - Ticker (bid/ask/last)
      - Kline/OHLCV history
      - Account balance
      - Order placement and cancellation
      - Open positions
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        api_passphrase: str = "",
        sandbox: bool = True,
    ) -> None:
        self._api_key = api_key or settings.bitget_api_key
        self._api_secret = api_secret or settings.bitget_api_secret
        self._api_passphrase = api_passphrase or settings.bitget_api_passphrase
        self._base_url = BASE_URL_SANDBOX if sandbox else BASE_URL_LIVE
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        prehash = f"{timestamp}{method.upper()}{path}{body}"
        return base64.b64encode(
            hmac.new(
                self._api_secret.encode("utf-8"),
                prehash.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode()

    def _headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        return {
            "ACCESS-KEY": self._api_key,
            "ACCESS-SIGN": self._sign(ts, method, path, body),
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-PASSPHRASE": self._api_passphrase,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Public endpoints (no auth required)
    # ------------------------------------------------------------------

    async def get_ticker(self, symbol: str, product_type: str = "USDT-FUTURES") -> dict[str, Any]:
        """Get current ticker: bid, ask, last, volume."""
        path = f"/api/v2/mix/market/ticker?symbol={symbol}&productType={product_type}"
        resp = await self._client.get(path)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "00000":
            raise RuntimeError(f"Bitget error: {data}")
        return data["data"][0] if isinstance(data["data"], list) else data["data"]

    async def get_orderbook(
        self, symbol: str, limit: int = 20, product_type: str = "USDT-FUTURES"
    ) -> dict[str, Any]:
        """Get order book snapshot."""
        path = (
            f"/api/v2/mix/market/merge-depth"
            f"?symbol={symbol}&productType={product_type}&limit={limit}"
        )
        resp = await self._client.get(path)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "00000":
            raise RuntimeError(f"Bitget error: {data}")
        return data["data"]

    async def get_klines(
        self,
        symbol: str,
        granularity: str = "1H",
        limit: int = 200,
        product_type: str = "USDT-FUTURES",
    ) -> list[list]:
        """Get OHLCV candles. granularity: 1m, 5m, 15m, 1H, 4H, 1D."""
        path = (
            f"/api/v2/mix/market/candles"
            f"?symbol={symbol}&productType={product_type}"
            f"&granularity={granularity}&limit={limit}"
        )
        resp = await self._client.get(path)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "00000":
            raise RuntimeError(f"Bitget error: {data}")
        # Returns list of [ts, open, high, low, close, baseVol, quoteVol]
        return data["data"]

    # ------------------------------------------------------------------
    # Private endpoints (auth required)
    # ------------------------------------------------------------------

    async def get_account_balance(self, product_type: str = "USDT-FUTURES") -> dict[str, Any]:
        """Get account equity and available balance."""
        path = f"/api/v2/mix/account/accounts?productType={product_type}"
        headers = self._headers("GET", path)
        resp = await self._client.get(path, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "00000":
            raise RuntimeError(f"Bitget error: {data}")
        return data["data"]

    async def get_positions(
        self, symbol: Optional[str] = None, product_type: str = "USDT-FUTURES"
    ) -> list[dict[str, Any]]:
        """Get open positions."""
        path = f"/api/v2/mix/position/all-position?productType={product_type}"
        if symbol:
            path += f"&symbol={symbol}"
        headers = self._headers("GET", path)
        resp = await self._client.get(path, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "00000":
            raise RuntimeError(f"Bitget error: {data}")
        return data["data"]

    async def place_order(
        self,
        symbol: str,
        side: str,           # "buy" or "sell"
        trade_side: str,     # "open" or "close"
        size: str,
        order_type: str = "market",
        product_type: str = "USDT-FUTURES",
        margin_mode: str = "crossed",
        leverage: str = "1",
        client_oid: Optional[str] = None,
    ) -> dict[str, Any]:
        """Place a futures order. Returns order ID on success."""
        import json
        path = "/api/v2/mix/order/place-order"
        body_dict: dict[str, Any] = {
            "symbol": symbol,
            "productType": product_type,
            "marginMode": margin_mode,
            "marginCoin": "USDT",
            "size": size,
            "side": side,
            "tradeSide": trade_side,
            "orderType": order_type,
            "leverage": leverage,
        }
        if client_oid:
            body_dict["clientOid"] = client_oid
        body = json.dumps(body_dict)
        headers = self._headers("POST", path, body)
        resp = await self._client.post(path, content=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "00000":
            raise RuntimeError(f"Bitget order error: {data}")
        return data["data"]

    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
        product_type: str = "USDT-FUTURES",
    ) -> dict[str, Any]:
        """Cancel an open order."""
        import json
        path = "/api/v2/mix/order/cancel-order"
        body = json.dumps({"symbol": symbol, "productType": product_type, "orderId": order_id})
        headers = self._headers("POST", path, body)
        resp = await self._client.post(path, content=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "00000":
            raise RuntimeError(f"Bitget cancel error: {data}")
        return data["data"]

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
