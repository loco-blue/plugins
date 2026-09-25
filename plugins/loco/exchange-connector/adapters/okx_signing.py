"""Shared OKX request-signing helpers.

Spot and futures/swap use the same auth mechanism - only `instId` format
and `tdMode` differ between markets, which is why this lives outside both
adapters.
"""

from datetime import datetime, timezone
from typing import Any

from .signing import hmac_sha256_base64


def okx_headers(
    credentials: dict[str, Any],
    testnet: bool,
    method: str,
    request_path: str,
    body: str = "",
) -> dict[str, str]:
    """Build OKX's required auth headers, signing exactly `body` as given -
    callers must pass the SAME string they will send on the wire (see
    `okx_spot.py`'s `place_order` method's comment about `content=` vs
    `json=`)."""
    api_key = credentials.get("api_key")
    api_secret = credentials.get("api_secret")
    passphrase = credentials.get("api_passphrase")
    if not (api_key and api_secret and passphrase):
        raise ValueError(
            "OKX credentials require 'api_key', 'api_secret', 'api_passphrase'"
        )
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
    if testnet:
        headers["x-simulated-trading"] = "1"
    return headers


def okx_unwrap(raw: dict[str, Any]) -> list[Any]:
    """Return `raw["data"]`, raising on OKX's HTTP-200 error envelope.

    OKX signals failures with HTTP 200 plus a non-"0" top-level `code`
    (e.g. `{"code": "50113", "msg": "Invalid Sign", "data": []}`), which
    `raise_for_status()` cannot see.
    """
    if raw.get("code") != "0":
        raise ValueError(f"OKX error {raw.get('code')}: {raw.get('msg')}")
    return raw["data"]
