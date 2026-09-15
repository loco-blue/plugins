from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.okx import OkxAdapter

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


async def test_get_klines_normalizes_raw_okx_rows(client):
    raw = {
        "code": "0",
        "data": [
            ["1700000000000", "42000.1", "42100.0", "41950.5", "42050.25", "12.345", "x", "x", "x"]
        ],
    }
    client.get = AsyncMock(return_value=_json_response(raw))
    adapter = OkxAdapter(client, CREDENTIALS, testnet=True)

    klines = await adapter.get_klines("BTC-USDT", "1m")

    assert klines == [
        {
            "open_time": "1700000000000",
            "open": 42000.1,
            "high": 42100.0,
            "low": 41950.5,
            "close": 42050.25,
            "volume": 12.345,
        }
    ]
    assert client.get.call_args.kwargs["headers"]["x-simulated-trading"] == "1"


async def test_place_order_signs_with_demo_header_and_normalizes(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {
                "code": "0",
                "data": [
                    {
                        "ordId": "ord-1",
                        "clOrdId": "wf-1-BTC-USDT-5",
                        "state": "filled",
                        "fillSz": "0.01",
                        "avgPx": "42050.0",
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
        "status": "filled",
        "filled_qty": 0.01,
        "avg_price": 42050.0,
    }
    headers = client.post.call_args.kwargs["headers"]
    for key in ("OK-ACCESS-KEY", "OK-ACCESS-SIGN", "OK-ACCESS-PASSPHRASE", "OK-ACCESS-TIMESTAMP"):
        assert key in headers
    assert headers["x-simulated-trading"] == "1"
    body = client.post.call_args.kwargs["json"]
    assert body["clOrdId"] == "wf-1-BTC-USDT-5"


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


async def test_cancel_order_normalizes_response(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {"code": "0", "data": [{"ordId": "ord-1", "sCode": "0"}]}
        )
    )
    adapter = OkxAdapter(client, CREDENTIALS, testnet=True)

    result = await adapter.cancel_order("BTC-USDT", "ord-1")

    assert result == {"order_id": "ord-1", "status": "canceled"}
