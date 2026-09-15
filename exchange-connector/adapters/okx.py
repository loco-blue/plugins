"""OKX adapter - demo trading (testnet-equivalent) by default.

Docs: https://www.okx.com/docs-v5/en/
Demo trading is toggled via the `x-simulated-trading: 1` header, not a
different host - both demo and live use `https://www.okx.com`.
"""

import json
from datetime import datetime, timezone
from typing import Any

from .base import ExchangeAdapter
from .signing import hmac_sha256_base64

_BASE_URL = "https://www.okx.com"


class OkxAdapter(ExchangeAdapter):
    """Adapter for OKX v5 REST API."""

    def _creds(self) -> tuple[str, str, str]:
        api_key = self.credentials.get("api_key")
        api_secret = self.credentials.get("api_secret")
        passphrase = self.credentials.get("api_passphrase")
        if not (api_key and api_secret and passphrase):
            raise ValueError(
                "OKX credentials require 'api_key', 'api_secret', 'api_passphrase'"
            )
        return api_key, api_secret, passphrase

    def _headers(
        self, method: str, request_path: str, body: str = ""
    ) -> dict[str, str]:
        api_key, api_secret, passphrase = self._creds()
        timestamp = (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        payload = f"{timestamp}{method}{request_path}{body}"
        headers = {
            "OK-ACCESS-KEY": api_key,
            "OK-ACCESS-SIGN": hmac_sha256_base64(api_secret, payload),
            "OK-ACCESS-PASSPHRASE": passphrase,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }
        if self.testnet:
            headers["x-simulated-trading"] = "1"
        return headers

    @staticmethod
    def _unwrap(raw: dict[str, Any]) -> list[Any]:
        """Return `raw["data"]`, raising on OKX's HTTP-200 error envelope.

        OKX signals failures with HTTP 200 plus a non-"0" top-level `code`
        (e.g. `{"code": "50113", "msg": "Invalid Sign", "data": []}`), which
        `raise_for_status()` cannot see - without this check the caller would
        crash on an empty `data` list instead of reporting the real error.
        """
        if raw.get("code") != "0":
            raise ValueError(
                f"OKX error {raw.get('code')}: {raw.get('msg')}"
            )
        return raw["data"]

    async def get_klines(
        self, symbol: str, interval: str
    ) -> list[dict[str, Any]]:
        request_path = f"/api/v5/market/candles?instId={symbol}&bar={interval}"
        response = await self.client.get(
            f"{_BASE_URL}{request_path}",
            headers=self._headers("GET", request_path),
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
            for row in reversed(self._unwrap(response.json()))
        ]

    async def place_order(
        self, symbol: str, side: str, quantity: float, client_order_id: str
    ) -> dict[str, Any]:
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
            headers=self._headers("POST", request_path, body),
            # Send the exact bytes we signed: `json=body_dict` would let httpx
            # re-serialize with different separators, breaking OK-ACCESS-SIGN.
            content=body.encode("utf-8"),
        )
        response.raise_for_status()
        raw = self._unwrap(response.json())[0]
        if raw.get("sCode") != "0":
            raise ValueError(f"OKX order rejected: {raw.get('sMsg')}")
        # OKX's place-order response is an acknowledgement only - it carries
        # {ordId, clOrdId, tag, ts, sCode, sMsg} and no fill data (unlike
        # Binance, whose order response reports status/executedQty). A caller
        # that needs real fill status must call get_positions afterwards.
        return {
            "order_id": raw["ordId"],
            "client_order_id": raw.get("clOrdId", client_order_id),
            "status": "live",
            "filled_qty": 0.0,
            "avg_price": 0.0,
        }

    # NOTE: place_order uses tdMode "cash" (spot), but this endpoint is
    # /api/v5/account/positions, which only reports derivatives positions -
    # a spot order placed through this plugin will never appear here.
    async def get_positions(self, symbol: str) -> list[dict[str, Any]]:
        request_path = f"/api/v5/account/positions?instId={symbol}"
        response = await self.client.get(
            f"{_BASE_URL}{request_path}",
            headers=self._headers("GET", request_path),
        )
        response.raise_for_status()
        positions = []
        for row in self._unwrap(response.json()):
            size = float(row.get("pos", 0))
            if size == 0:
                continue
            positions.append(
                {
                    "symbol": row["instId"],
                    "side": row.get("posSide", "long"),
                    "entry_price": float(row.get("avgPx", 0)),
                    "quantity": abs(size),
                }
            )
        return positions

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        request_path = "/api/v5/trade/cancel-order"
        body_dict = {"instId": symbol, "ordId": order_id}
        body = json.dumps(body_dict)
        response = await self.client.post(
            f"{_BASE_URL}{request_path}",
            headers=self._headers("POST", request_path, body),
            # Send the exact bytes we signed - see place_order.
            content=body.encode("utf-8"),
        )
        response.raise_for_status()
        raw = self._unwrap(response.json())[0]
        status = "canceled" if raw.get("sCode") == "0" else "failed"
        return {"order_id": raw["ordId"], "status": status}
