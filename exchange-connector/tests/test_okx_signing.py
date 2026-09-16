import pytest

from adapters.okx_signing import okx_headers, okx_unwrap
from adapters.signing import hmac_sha256_base64

CREDENTIALS = {"api_key": "ak", "api_secret": "as", "api_passphrase": "pp"}


def test_okx_headers_includes_simulated_trading_when_testnet():
    headers = okx_headers(CREDENTIALS, True, "GET", "/api/v5/account/balance")
    assert headers["x-simulated-trading"] == "1"
    assert headers["OK-ACCESS-KEY"] == "ak"
    assert headers["OK-ACCESS-PASSPHRASE"] == "pp"


def test_okx_headers_omits_simulated_trading_when_live():
    headers = okx_headers(CREDENTIALS, False, "GET", "/api/v5/account/balance")
    assert "x-simulated-trading" not in headers


def test_okx_headers_signs_the_exact_payload():
    headers = okx_headers(CREDENTIALS, True, "POST", "/api/v5/trade/order", "{}")
    expected = hmac_sha256_base64(
        CREDENTIALS["api_secret"],
        f"{headers['OK-ACCESS-TIMESTAMP']}POST/api/v5/trade/order{{}}",
    )
    assert headers["OK-ACCESS-SIGN"] == expected


def test_okx_headers_raises_when_credentials_incomplete():
    with pytest.raises(ValueError, match="passphrase"):
        okx_headers({"api_key": "ak", "api_secret": "as"}, True, "GET", "/x")


def test_okx_unwrap_returns_data_on_success():
    assert okx_unwrap({"code": "0", "data": [{"a": 1}]}) == [{"a": 1}]


def test_okx_unwrap_raises_on_error_envelope():
    with pytest.raises(ValueError, match="Invalid Sign"):
        okx_unwrap({"code": "50113", "msg": "Invalid Sign", "data": []})
