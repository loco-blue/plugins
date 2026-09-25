"""OKX USDT-margined perpetual swap adapter - demo trading (testnet-
equivalent) by default, one-way/net position mode, cross margin.

Docs: https://www.okx.com/docs-v5/en/
Isolated margin mode is out of scope for this phase - every order/leverage
call uses `mgnMode`/`tdMode: "cross"` unconditionally.
"""

import json
from typing import Any

from .base import FuturesAdapter
from .okx_signing import okx_headers, okx_unwrap

_BASE_URL = "https://www.okx.com"

_ORDER_TYPES = {
    "market": "market",
    "stop_market": "conditional",
    "take_profit_market": "conditional",
}


class OkxFuturesAdapter(FuturesAdapter):
    """Adapter for OKX v5 REST API, USDT-margined perpetual swaps
    (`tdMode: cross`), one-way/net position mode."""

    async def get_klines(
        self, symbol: str, interval: str
    ) -> list[dict[str, Any]]:
        request_path = f"/api/v5/market/candles?instId={symbol}&bar={interval}"
        response = await self.client.get(
            f"{_BASE_URL}{request_path}",
            headers=okx_headers(self.credentials, self.testnet, "GET", request_path),
        )
        response.raise_for_status()
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
        okx_ord_type = _ORDER_TYPES.get(order_type)
        if okx_ord_type is None:
            raise ValueError(f"unsupported order_type {order_type!r}")
        if okx_ord_type != "market" and stop_price is None:
            raise ValueError(f"order_type {order_type!r} requires stop_price")

        request_path = "/api/v5/trade/order"
        body_dict: dict[str, Any] = {
            "instId": symbol,
            "tdMode": "cross",
            "side": side.lower(),
            "ordType": okx_ord_type,
            "sz": str(quantity),
            "clOrdId": client_order_id,
            "reduceOnly": reduce_only,
        }
        if okx_ord_type == "conditional":
            is_tp = order_type == "take_profit_market"
            trigger_key = "tpTriggerPx" if is_tp else "slTriggerPx"
            order_key = "tpOrdPx" if is_tp else "slOrdPx"
            body_dict[trigger_key] = str(stop_price)
            body_dict[order_key] = "-1"  # market execution once triggered
        body = json.dumps(body_dict)
        response = await self.client.post(
            f"{_BASE_URL}{request_path}",
            headers=okx_headers(self.credentials, self.testnet, "POST", request_path, body),
            content=body.encode("utf-8"),
        )
        response.raise_for_status()
        raw = okx_unwrap(response.json())[0]
        if raw.get("sCode") != "0":
            raise ValueError(f"OKX order rejected: {raw.get('sMsg')}")
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

    async def get_positions(self, symbol: str) -> list[dict[str, Any]]:
        request_path = f"/api/v5/account/positions?instId={symbol}"
        response = await self.client.get(
            f"{_BASE_URL}{request_path}",
            headers=okx_headers(self.credentials, self.testnet, "GET", request_path),
        )
        response.raise_for_status()
        positions = []
        for row in okx_unwrap(response.json()):
            size = float(row.get("pos", 0))
            if size == 0:
                continue
            side = row.get("posSide")
            if side not in ("long", "short"):
                # In the one-way/net position mode this plugin exclusively
                # supports, OKX returns posSide: "net" and carries direction
                # in the sign of `pos` instead. Only trust an explicit
                # long/short posSide (some other position-mode configs use
                # it); never default a missing/"net" value to "long".
                side = "long" if size > 0 else "short"
            positions.append(
                {
                    "symbol": row["instId"],
                    "side": side,
                    "entry_price": float(row.get("avgPx", 0)),
                    "quantity": abs(size),
                }
            )
        return positions

    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        request_path = "/api/v5/account/set-leverage"
        body_dict = {"instId": symbol, "lever": str(leverage), "mgnMode": "cross"}
        body = json.dumps(body_dict)
        response = await self.client.post(
            f"{_BASE_URL}{request_path}",
            headers=okx_headers(self.credentials, self.testnet, "POST", request_path, body),
            content=body.encode("utf-8"),
        )
        response.raise_for_status()
        raw = okx_unwrap(response.json())[0]
        return {
            "symbol": raw.get("instId", symbol),
            "leverage": int(raw.get("lever", leverage)),
            "status": "ok",
        }
