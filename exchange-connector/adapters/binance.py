"""Binance Spot adapter - testnet by default.

Docs: https://binance-docs.github.io/apidocs/spot/en/
"""

import time
from typing import Any
from urllib.parse import urlencode

from .base import ExchangeAdapter
from .signing import hmac_sha256_hex

_BASE_URLS = {
    True: "https://testnet.binance.vision",
    False: "https://api.binance.com",
}


class BinanceAdapter(ExchangeAdapter):
    """Adapter for Binance Spot REST API."""

    def _base_url(self) -> str:
        return _BASE_URLS[self.testnet]

    def _api_key(self) -> str:
        api_key = self.credentials.get("api_key")
        if not api_key:
            raise ValueError("Binance credentials missing 'api_key'")
        return api_key

    def _api_secret(self) -> str:
        api_secret = self.credentials.get("api_secret")
        if not api_secret:
            raise ValueError("Binance credentials missing 'api_secret'")
        return api_secret

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params)
        params["signature"] = hmac_sha256_hex(self._api_secret(), query)
        return params

    async def get_klines(
        self, symbol: str, interval: str
    ) -> list[dict[str, Any]]:
        response = await self.client.get(
            f"{self._base_url()}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": 100},
        )
        response.raise_for_status()
        raw = response.json()
        return [
            {
                "open_time": str(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in raw
        ]

    async def place_order(
        self, symbol: str, side: str, quantity: float, client_order_id: str
    ) -> dict[str, Any]:
        params = self._sign(
            {
                "symbol": symbol,
                "side": side.upper(),
                "type": "MARKET",
                "quantity": quantity,
                "newClientOrderId": client_order_id,
            }
        )
        response = await self.client.post(
            f"{self._base_url()}/api/v3/order",
            params=params,
            headers={"X-MBX-APIKEY": self._api_key()},
        )
        response.raise_for_status()
        raw = response.json()
        filled_qty = float(raw.get("executedQty", 0))
        quote_qty = float(raw.get("cummulativeQuoteQty", 0))
        avg_price = (quote_qty / filled_qty) if filled_qty else 0.0
        return {
            "order_id": str(raw["orderId"]),
            "client_order_id": raw.get("clientOrderId", client_order_id),
            "status": raw["status"],
            "filled_qty": filled_qty,
            "avg_price": avg_price,
        }

    async def get_positions(self, symbol: str) -> list[dict[str, Any]]:
        params = self._sign({"symbol": symbol})
        response = await self.client.get(
            f"{self._base_url()}/api/v3/openOrders",
            params=params,
            headers={"X-MBX-APIKEY": self._api_key()},
        )
        response.raise_for_status()
        raw = response.json()
        positions = []
        for row in raw:
            amount = float(row.get("positionAmt", 0))
            if amount == 0:
                continue
            positions.append(
                {
                    "symbol": row["symbol"],
                    "side": "long" if amount > 0 else "short",
                    "entry_price": float(row.get("entryPrice", 0)),
                    "quantity": abs(amount),
                }
            )
        return positions

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        params = self._sign({"symbol": symbol, "orderId": order_id})
        response = await self.client.delete(
            f"{self._base_url()}/api/v3/order",
            params=params,
            headers={"X-MBX-APIKEY": self._api_key()},
        )
        response.raise_for_status()
        raw = response.json()
        return {"order_id": str(raw["orderId"]), "status": raw["status"]}
