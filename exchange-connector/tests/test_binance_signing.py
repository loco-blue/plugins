from urllib.parse import urlencode

import pytest

from adapters.binance_signing import binance_api_key, sign_binance_params
from adapters.signing import hmac_sha256_hex

CREDENTIALS = {"api_key": "ak", "api_secret": "as"}


def test_binance_api_key_returns_the_configured_key():
    assert binance_api_key(CREDENTIALS) == "ak"


def test_binance_api_key_raises_when_missing():
    with pytest.raises(ValueError, match="api_key"):
        binance_api_key({"api_secret": "as"})


def test_sign_binance_params_adds_a_correct_signature():
    signed = sign_binance_params(CREDENTIALS, {"symbol": "BTCUSDT"})
    assert "timestamp" in signed
    query = urlencode({k: v for k, v in signed.items() if k != "signature"})
    assert signed["signature"] == hmac_sha256_hex(CREDENTIALS["api_secret"], query)


def test_sign_binance_params_raises_when_secret_missing():
    with pytest.raises(ValueError, match="api_secret"):
        sign_binance_params({"api_key": "ak"}, {"symbol": "BTCUSDT"})
