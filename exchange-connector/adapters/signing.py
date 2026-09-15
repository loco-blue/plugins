"""Pure HMAC-SHA256 signing helpers shared by every exchange adapter.

No exchange-specific string-to-sign construction lives here - each adapter
builds its own payload string per that exchange's docs and calls one of
these two functions to turn it into a signature.
"""

import base64
import hashlib
import hmac


def hmac_sha256_hex(secret: str, payload: str) -> str:
    """Binance-style signature: hex digest of HMAC-SHA256(secret, payload)."""
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def hmac_sha256_base64(secret: str, payload: str) -> str:
    """OKX-style signature: base64 of the raw HMAC-SHA256(secret, payload) digest."""
    digest = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")
