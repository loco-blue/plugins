from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.okx import OkxAdapter
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
    # OKX /api/v5/market/candles returns rows NEWEST-first.
    raw = {
        "code": "0",
        "data": [
            ["1700000120000", "42100.0", "42200.0", "42050.0", "42150.0", "3.0", "x", "x", "x"],
            ["1700000060000", "42050.0", "42150.0", "42000.0", "42100.0", "2.0", "x", "x", "x"],
            ["1700000000000", "42000.1", "42100.0", "41950.5", "42050.25", "12.345", "x", "x", "x"],
        ],
    }
    client.get = AsyncMock(return_value=_json_response(raw))
    adapter = OkxAdapter(client, CREDENTIALS, testnet=True)

    klines = await adapter.get_klines("BTC-USDT", "1m")

    # Contract (adapters/base.py): oldest first - the OKX rows must be reversed.
    assert [k["open_time"] for k in klines] == [
        "1700000000000",
        "1700000060000",
        "1700000120000",
    ]
    assert [k["open_time"] for k in klines] == sorted(
        k["open_time"] for k in klines
    )
    assert klines[0] == {
        "open_time": "1700000000000",
        "open": 42000.1,
        "high": 42100.0,
        "low": 41950.5,
        "close": 42050.25,
        "volume": 12.345,
    }
    assert client.get.call_args.kwargs["headers"]["x-simulated-trading"] == "1"


async def test_get_klines_raises_on_okx_http_200_error_envelope(client):
    client.get = AsyncMock(
        return_value=_json_response(
            {"code": "50113", "msg": "Invalid Sign", "data": []}
        )
    )
    adapter = OkxAdapter(client, CREDENTIALS, testnet=True)

    with pytest.raises(ValueError, match="Invalid Sign"):
        await adapter.get_klines("BTC-USDT", "1m")


async def test_place_order_raises_on_okx_http_200_error_envelope(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {"code": "50113", "msg": "Invalid Sign", "data": []}
        )
    )
    adapter = OkxAdapter(client, CREDENTIALS, testnet=True)

    with pytest.raises(ValueError, match="50113"):
        await adapter.place_order("BTC-USDT", "buy", 0.01, "wf-1-BTC-USDT-5")


async def test_place_order_signs_the_exact_bytes_it_sends(client):
    # Real OKX place-order ack: no state/fillSz/avgPx.
    client.post = AsyncMock(
        return_value=_json_response(
            {
                "code": "0",
                "data": [
                    {
                        "ordId": "ord-1",
                        "clOrdId": "wf-1-BTC-USDT-5",
                        "tag": "",
                        "ts": "1700000000000",
                        "sCode": "0",
                        "sMsg": "",
                    }
                ],
            }
        )
    )
    adapter = OkxAdapter(client, CREDENTIALS, testnet=True)

    order = await adapter.place_order("BTC-USDT", "buy", 0.01, "wf-1-BTC-USDT-5")

    assert order == {
        "order_id": "ord-1",
        "client_order_id": "wf-1-BTC-USDT-5",
        "status": "live",
        "filled_qty": 0.0,
        "avg_price": 0.0,
    }
    kwargs = client.post.call_args.kwargs
    headers = kwargs["headers"]
    assert headers["x-simulated-trading"] == "1"
    assert headers["OK-ACCESS-KEY"] == "ak"
    assert headers["OK-ACCESS-PASSPHRASE"] == "pp"
    assert headers["Content-Type"] == "application/json"

    # The request must carry the raw bytes that were signed, not a re-serialized
    # `json=` payload (httpx would use different separators).
    assert "json" not in kwargs
    sent_body = kwargs["content"].decode("utf-8")
    assert '"clOrdId": "wf-1-BTC-USDT-5"' in sent_body

    expected_sign = hmac_sha256_base64(
        CREDENTIALS["api_secret"],
        f"{headers['OK-ACCESS-TIMESTAMP']}POST/api/v5/trade/order{sent_body}",
    )
    assert headers["OK-ACCESS-SIGN"] == expected_sign


async def test_place_order_raises_when_okx_rejects_the_order(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {
                "code": "0",
                "data": [
                    {
                        "ordId": "",
                        "clOrdId": "wf-1-BTC-USDT-5",
                        "sCode": "51008",
                        "sMsg": "Insufficient balance",
                    }
                ],
            }
        )
    )
    adapter = OkxAdapter(client, CREDENTIALS, testnet=True)

    with pytest.raises(ValueError, match="Insufficient balance"):
        await adapter.place_order("BTC-USDT", "buy", 0.01, "wf-1-BTC-USDT-5")


async def test_get_positions_normalizes_open_position(client):
    client.get = AsyncMock(
        return_value=_json_response(
            {
                "code": "0",
                "data": [
                    {"instId": "BTC-USDT", "posSide": "long", "avgPx": "42000.0", "pos": "0.01"}
                ],
            }
        )
    )
    adapter = OkxAdapter(client, CREDENTIALS, testnet=True)

    positions = await adapter.get_positions("BTC-USDT")

    assert positions == [
        {"symbol": "BTC-USDT", "side": "long", "entry_price": 42000.0, "quantity": 0.01}
    ]


async def test_cancel_order_normalizes_response_and_signs_sent_bytes(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {"code": "0", "data": [{"ordId": "ord-1", "sCode": "0"}]}
        )
    )
    adapter = OkxAdapter(client, CREDENTIALS, testnet=True)

    result = await adapter.cancel_order("BTC-USDT", "ord-1")

    assert result == {"order_id": "ord-1", "status": "canceled"}
    kwargs = client.post.call_args.kwargs
    assert "json" not in kwargs
    sent_body = kwargs["content"].decode("utf-8")
    expected_sign = hmac_sha256_base64(
        CREDENTIALS["api_secret"],
        f"{kwargs['headers']['OK-ACCESS-TIMESTAMP']}POST"
        f"/api/v5/trade/cancel-order{sent_body}",
    )
    assert kwargs["headers"]["OK-ACCESS-SIGN"] == expected_sign
