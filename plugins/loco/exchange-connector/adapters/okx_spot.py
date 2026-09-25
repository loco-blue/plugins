"""OKX Spot adapter - demo trading (testnet-equivalent) by default.

Docs: https://www.okx.com/docs-v5/en/
Demo trading is toggled via the `x-simulated-trading: 1` header, not a
different host - both demo and live use `https://www.okx.com`.
"""

import json
from typing import Any

from .base import ExchangeAdapter
from .okx_signing import okx_headers, okx_unwrap

_BASE_URL = "https://www.okx.com"


class OkxSpotAdapter(ExchangeAdapter):
    """Adapter for OKX v5 REST API, spot (`tdMode: cash`)."""

    async def get_klines(
        self, symbol: str, interval: str
    ) -> list[dict[str, Any]]:
        request_path = f"/api/v5/market/candles?instId={symbol}&bar={interval}"
        response = await self.client.get(
            f"{_BASE_URL}{request_path}",
            headers=okx_headers(self.credentials, self.testnet, "GET", request_path),
        )
        response.raise_for_status()
        # OKX returns candles newest-first; the shared contract (base.py) is
        # oldest-first, like Binance's already-ascending /api/v3/klines.
        return [
            {
                "open_time": row[0],
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in reversed(okx_unwrap(response.json()))
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
                "OKX spot only supports order_type='market' and "
                "reduce_only=False; stop/take-profit orders and reduce_only "
                "are futures-only"
            )
        request_path = "/api/v5/trade/order"
        body_dict = {
            "instId": symbol,
            "tdMode": "cash",
            "side": side.lower(),
            "ordType": "market",
            "sz": str(quantity),
            "clOrdId": client_order_id,
        }
        body = json.dumps(body_dict)
        response = await self.client.post(
            f"{_BASE_URL}{request_path}",
            headers=okx_headers(self.credentials, self.testnet, "POST", request_path, body),
            # Send the exact bytes we signed: `json=body_dict` would let httpx
            # re-serialize with different separators, breaking OK-ACCESS-SIGN.
            content=body.encode("utf-8"),
        )
        response.raise_for_status()
        raw = okx_unwrap(response.json())[0]
        if raw.get("sCode") != "0":
            raise ValueError(f"OKX order rejected: {raw.get('sMsg')}")
        # OKX's place-order response is an acknowledgement only - see
        # README's "Known simplifications".
        return {
            "order_id": raw["ordId"],
            "client_order_id": raw.get("clOrdId", client_order_id),
            "status": "live",
            "filled_qty": 0.0,
            "avg_price": 0.0,
        }

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        request_path = "/api/v5/trade/cancel-order"
        body_dict = {"instId": symbol, "ordId": order_id}
        body = json.dumps(body_dict)
        response = await self.client.post(
            f"{_BASE_URL}{request_path}",
            headers=okx_headers(self.credentials, self.testnet, "POST", request_path, body),
            content=body.encode("utf-8"),
        )
        response.raise_for_status()
        raw = okx_unwrap(response.json())[0]
        status = "canceled" if raw.get("sCode") == "0" else "failed"
        return {"order_id": raw["ordId"], "status": status}

    async def get_balance(self) -> list[dict[str, Any]]:
        request_path = "/api/v5/account/balance"
        response = await self.client.get(
            f"{_BASE_URL}{request_path}",
            headers=okx_headers(self.credentials, self.testnet, "GET", request_path),
        )
        response.raise_for_status()
        balances = []
        for account in okx_unwrap(response.json()):
            for row in account.get("details", []):
                free = float(row.get("availBal", 0))
                locked = float(row.get("frozenBal", 0))
                if free == 0 and locked == 0:
                    continue
                balances.append({"asset": row["ccy"], "free": free, "locked": locked})
        return balances
