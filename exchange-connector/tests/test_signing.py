import hashlib
import hmac as hmac_stdlib

from adapters.signing import hmac_sha256_base64, hmac_sha256_hex


def test_hex_signature_matches_stdlib_hmac():
    secret = "s3cr3t"
    payload = "symbol=BTCUSDT&timestamp=1700000000000"
    expected = hmac_stdlib.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    assert hmac_sha256_hex(secret, payload) == expected


def test_base64_signature_matches_stdlib_hmac():
    import base64

    secret = "s3cr3t"
    payload = "1700000000000GET/api/v5/account/balance"
    expected = base64.b64encode(
        hmac_stdlib.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    ).decode()
    assert hmac_sha256_base64(secret, payload) == expected


def test_exchange_adapter_cannot_be_instantiated_directly():
    from adapters.base import ExchangeAdapter

    import pytest

    with pytest.raises(TypeError):
        ExchangeAdapter(client=None, credentials={})
