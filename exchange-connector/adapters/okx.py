"""OKX adapter - demo trading (testnet-equivalent) by default.

Docs: https://www.okx.com/docs-v5/en/
Demo trading is toggled via the `x-simulated-trading: 1` header, not a
different host - both demo and live use `https://www.okx.com`.
"""

import json
import time
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

    async def get_klines(
        self, symbol: str, interval: str
    ) -> list[dict[str, Any]]:
        request_path = f"/api/v5/market/candles?instId={symbol}&bar={interval}"
        response = await self.client.get(
            f"{_BASE_URL}{request_path}",
            headers=self._headers("GET", request_path),
        )
        response.raise_for_status()
        raw = response.json()
        return [
            {
                "open_time": row[0],
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in raw["data"]
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
            json=body_dict,
        )
        response.raise_for_status()
        raw = response.json()["data"][0]
        return {
            "order_id": raw["ordId"],
            "client_order_id": raw.get("clOrdId", client_order_id),
            "status": raw["state"],
            "filled_qty": float(raw.get("fillSz", 0)),
            "avg_price": float(raw.get("avgPx", 0)),
        }

    async def get_positions(self, symbol: str) -> list[dict[str, Any]]:
        request_path = f"/api/v5/account/positions?instId={symbol}"
        response = await self.client.get(
            f"{_BASE_URL}{request_path}",
            headers=self._headers("GET", request_path),
        )
        response.raise_for_status()
        raw = response.json()
        positions = []
        for row in raw["data"]:
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
            json=body_dict,
        )
        response.raise_for_status()
        raw = response.json()["data"][0]
        status = "canceled" if raw.get("sCode") == "0" else "failed"
        return {"order_id": raw["ordId"], "status": status}
