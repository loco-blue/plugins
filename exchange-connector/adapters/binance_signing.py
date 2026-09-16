"""Shared Binance request-signing helpers.

Spot and futures use the same auth mechanism - HMAC-SHA256 hex over the
query string, `X-MBX-APIKEY` header - only the host and endpoint paths
differ between markets, which is why this lives outside both adapters.
"""

import time
from typing import Any
from urllib.parse import urlencode

from .signing import hmac_sha256_hex


def binance_api_key(credentials: dict[str, Any]) -> str:
    """Return the configured API key, or raise if missing."""
    api_key = credentials.get("api_key")
    if not api_key:
        raise ValueError("Binance credentials missing 'api_key'")
    return api_key


def sign_binance_params(
    credentials: dict[str, Any], params: dict[str, Any]
) -> dict[str, Any]:
    """Return `params` with `timestamp`/`signature` added, HMAC-signed."""
    api_secret = credentials.get("api_secret")
    if not api_secret:
        raise ValueError("Binance credentials missing 'api_secret'")
    params = dict(params)
    params["timestamp"] = int(time.time() * 1000)
    query = urlencode(params)
    params["signature"] = hmac_sha256_hex(api_secret, query)
    return params
