"""Binance USDT-margined Futures adapter - testnet by default, one-way
(net) position mode.

Docs: https://binance-docs.github.io/apidocs/futures/en/
"""

from typing import Any

from .base import FuturesAdapter
from .binance_signing import binance_api_key, sign_binance_params

_BASE_URLS = {
    True: "https://testnet.binancefuture.com",
    False: "https://fapi.binance.com",
}

_ORDER_TYPES = {
    "market": "MARKET",
    "stop_market": "STOP_MARKET",
    "take_profit_market": "TAKE_PROFIT_MARKET",
}


class BinanceFuturesAdapter(FuturesAdapter):
    """Adapter for Binance USDT-M Futures REST API, one-way position mode."""

    def _base_url(self) -> str:
        return _BASE_URLS[self.testnet]

    async def get_klines(
        self, symbol: str, interval: str
    ) -> list[dict[str, Any]]:
        response = await self.client.get(
            f"{self._base_url()}/fapi/v1/klines",
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
        binance_type = _ORDER_TYPES.get(order_type)
        if binance_type is None:
            raise ValueError(f"unsupported order_type {order_type!r}")
        if binance_type != "MARKET" and stop_price is None:
            raise ValueError(f"order_type {order_type!r} requires stop_price")

        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": binance_type,
            "quantity": quantity,
            "newClientOrderId": client_order_id,
            "reduceOnly": "true" if reduce_only else "false",
        }
        if stop_price is not None:
            params["stopPrice"] = stop_price
        params = sign_binance_params(self.credentials, params)

        response = await self.client.post(
            f"{self._base_url()}/fapi/v1/order",
            params=params,
            headers={"X-MBX-APIKEY": binance_api_key(self.credentials)},
        )
        response.raise_for_status()
        raw = response.json()
        return {
            "order_id": str(raw["orderId"]),
            "client_order_id": raw.get("clientOrderId", client_order_id),
            "status": raw["status"],
            "filled_qty": float(raw.get("executedQty", 0)),
            "avg_price": float(raw.get("avgPrice", 0)),
        }

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        params = sign_binance_params(
            self.credentials, {"symbol": symbol, "orderId": order_id}
        )
        response = await self.client.delete(
            f"{self._base_url()}/fapi/v1/order",
            params=params,
            headers={"X-MBX-APIKEY": binance_api_key(self.credentials)},
        )
        response.raise_for_status()
        raw = response.json()
        return {"order_id": str(raw["orderId"]), "status": raw["status"]}

    async def get_balance(self) -> list[dict[str, Any]]:
        params = sign_binance_params(self.credentials, {})
        response = await self.client.get(
            f"{self._base_url()}/fapi/v2/balance",
            params=params,
            headers={"X-MBX-APIKEY": binance_api_key(self.credentials)},
        )
        response.raise_for_status()
        raw = response.json()
        balances = []
        for row in raw:
            total = float(row.get("balance", 0))
            free = float(row.get("availableBalance", 0))
            if total == 0 and free == 0:
                continue
            balances.append(
                {"asset": row["asset"], "free": free, "locked": max(total - free, 0.0)}
            )
        return balances

    async def get_positions(self, symbol: str) -> list[dict[str, Any]]:
        params = sign_binance_params(self.credentials, {"symbol": symbol})
        response = await self.client.get(
            f"{self._base_url()}/fapi/v2/positionRisk",
            params=params,
            headers={"X-MBX-APIKEY": binance_api_key(self.credentials)},
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

    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        params = sign_binance_params(
            self.credentials, {"symbol": symbol, "leverage": leverage}
        )
        response = await self.client.post(
            f"{self._base_url()}/fapi/v1/leverage",
            params=params,
            headers={"X-MBX-APIKEY": binance_api_key(self.credentials)},
        )
        response.raise_for_status()
        raw = response.json()
        return {
            "symbol": raw.get("symbol", symbol),
            "leverage": int(raw.get("leverage", leverage)),
            "status": "ok",
        }
