"""Binance Spot adapter - testnet by default.

Docs: https://binance-docs.github.io/apidocs/spot/en/
"""

from typing import Any

from .base import ExchangeAdapter
from .binance_signing import binance_api_key, sign_binance_params

_BASE_URLS = {
    True: "https://testnet.binance.vision",
    False: "https://api.binance.com",
}


class BinanceSpotAdapter(ExchangeAdapter):
    """Adapter for Binance Spot REST API."""

    def _base_url(self) -> str:
        return _BASE_URLS[self.testnet]

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
        self,
        symbol: str,
        side: str,
        quantity: float,
        client_order_id: str,
        order_type: str = "market",
        stop_price: float | None = None,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        if order_type != "market" or reduce_only:
            raise ValueError(
                "Binance spot only supports order_type='market' and "
                "reduce_only=False; stop/take-profit orders and reduce_only "
                "are futures-only"
            )
        params = sign_binance_params(
            self.credentials,
            {
                "symbol": symbol,
                "side": side.upper(),
                "type": "MARKET",
                "quantity": quantity,
                "newClientOrderId": client_order_id,
            },
        )
        response = await self.client.post(
            f"{self._base_url()}/api/v3/order",
            params=params,
            headers={"X-MBX-APIKEY": binance_api_key(self.credentials)},
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

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        params = sign_binance_params(
            self.credentials, {"symbol": symbol, "orderId": order_id}
        )
        response = await self.client.delete(
            f"{self._base_url()}/api/v3/order",
            params=params,
            headers={"X-MBX-APIKEY": binance_api_key(self.credentials)},
        )
        response.raise_for_status()
        raw = response.json()
        return {"order_id": str(raw["orderId"]), "status": raw["status"]}

    async def get_balance(self) -> list[dict[str, Any]]:
        params = sign_binance_params(self.credentials, {})
        response = await self.client.get(
            f"{self._base_url()}/api/v3/account",
            params=params,
            headers={"X-MBX-APIKEY": binance_api_key(self.credentials)},
        )
        response.raise_for_status()
        raw = response.json()
        balances = []
        for row in raw.get("balances", []):
            free = float(row.get("free", 0))
            locked = float(row.get("locked", 0))
            if free == 0 and locked == 0:
                continue
            balances.append({"asset": row["asset"], "free": free, "locked": locked})
        return balances
