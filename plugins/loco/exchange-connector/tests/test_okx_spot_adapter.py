from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.okx_spot import OkxSpotAdapter
from adapters.signing import hmac_sha256_base64

CREDENTIALS = {
    "auth_type": "api_key",
    "api_key": "ak",
    "api_secret": "as",
    "api_passphrase": "pp",
}


def _json_response(payload, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


@pytest.fixture
def client():
    return MagicMock()


async def test_get_klines_normalizes_and_reverses_okx_newest_first_rows(client):
    raw = {
        "code": "0",
        "data": [
            ["1700000060000", "1", "2", "0.5", "1.5", "2.0", "x", "x", "x"],
            ["1700000000000", "0.9", "1.1", "0.8", "1.0", "1.0", "x", "x", "x"],
        ],
    }
    client.get = AsyncMock(return_value=_json_response(raw))
    adapter = OkxSpotAdapter(client, CREDENTIALS, testnet=True)

    klines = await adapter.get_klines("BTC-USDT", "1m")

    assert [k["open_time"] for k in klines] == ["1700000000000", "1700000060000"]


async def test_place_order_signs_the_exact_bytes_it_sends(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {
                "code": "0",
                "data": [
                    {"ordId": "ord-1", "clOrdId": "wf-1-BTC-USDT-5", "sCode": "0", "sMsg": ""}
                ],
            }
        )
    )
    adapter = OkxSpotAdapter(client, CREDENTIALS, testnet=True)

    order = await adapter.place_order("BTC-USDT", "buy", 0.01, "wf-1-BTC-USDT-5")

    assert order == {
        "order_id": "ord-1",
        "client_order_id": "wf-1-BTC-USDT-5",
        "status": "live",
        "filled_qty": 0.0,
        "avg_price": 0.0,
    }
    kwargs = client.post.call_args.kwargs
    assert "json" not in kwargs
    sent_body = kwargs["content"].decode("utf-8")
    expected_sign = hmac_sha256_base64(
        CREDENTIALS["api_secret"],
        f"{kwargs['headers']['OK-ACCESS-TIMESTAMP']}POST/api/v5/trade/order{sent_body}",
    )
    assert kwargs["headers"]["OK-ACCESS-SIGN"] == expected_sign


async def test_place_order_rejects_non_market_order_type(client):
    adapter = OkxSpotAdapter(client, CREDENTIALS, testnet=True)
    with pytest.raises(ValueError, match="order_type"):
        await adapter.place_order(
            "BTC-USDT", "buy", 0.01, "wf-1", order_type="stop_market", stop_price=100.0
        )


async def test_place_order_rejects_reduce_only(client):
    adapter = OkxSpotAdapter(client, CREDENTIALS, testnet=True)
    with pytest.raises(ValueError, match="reduce_only"):
        await adapter.place_order("BTC-USDT", "buy", 0.01, "wf-1", reduce_only=True)


async def test_cancel_order_normalizes_response(client):
    client.post = AsyncMock(
        return_value=_json_response({"code": "0", "data": [{"ordId": "ord-1", "sCode": "0"}]})
    )
    adapter = OkxSpotAdapter(client, CREDENTIALS, testnet=True)

    result = await adapter.cancel_order("BTC-USDT", "ord-1")

    assert result == {"order_id": "ord-1", "status": "canceled"}


async def test_get_balance_filters_zero_balances(client):
    client.get = AsyncMock(
        return_value=_json_response(
            {
                "code": "0",
                "data": [
                    {
                        "details": [
                            {"ccy": "USDT", "availBal": "500.0", "frozenBal": "0"},
                            {"ccy": "ETH", "availBal": "0", "frozenBal": "0"},
                        ]
                    }
                ],
            }
        )
    )
    adapter = OkxSpotAdapter(client, CREDENTIALS, testnet=True)

    balances = await adapter.get_balance()

    assert balances == [{"asset": "USDT", "free": 500.0, "locked": 0.0}]
