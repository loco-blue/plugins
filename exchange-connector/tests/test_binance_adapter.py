from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.binance import BinanceAdapter

CREDENTIALS = {"auth_type": "api_key", "api_key": "ak", "api_secret": "as"}


def _json_response(payload, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


@pytest.fixture
def client():
    return MagicMock()


async def test_get_klines_normalizes_raw_binance_arrays(client):
    raw = [
        [1700000000000, "42000.10", "42100.00", "41950.50", "42050.25", "12.345",
         1700000059999, "0", 0, "0", "0", "0"],
    ]
    client.get = AsyncMock(return_value=_json_response(raw))
    adapter = BinanceAdapter(client, CREDENTIALS, testnet=True)

    klines = await adapter.get_klines("BTCUSDT", "1m")

    assert klines == [
        {
            "open_time": "1700000000000",
            "open": 42000.10,
            "high": 42100.00,
            "low": 41950.50,
            "close": 42050.25,
            "volume": 12.345,
        }
    ]
    called_url = client.get.call_args.args[0]
    assert called_url == "https://testnet.binance.vision/api/v3/klines"
    assert client.get.call_args.kwargs["params"] == {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "limit": 100,
    }


async def test_place_order_signs_the_request_and_normalizes_response(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {
                "orderId": 991,
                "clientOrderId": "wf-1-BTCUSDT-5",
                "status": "FILLED",
                "executedQty": "0.01000000",
                "cummulativeQuoteQty": "420.50",
            }
        )
    )
    adapter = BinanceAdapter(client, CREDENTIALS, testnet=True)

    order = await adapter.place_order("BTCUSDT", "buy", 0.01, "wf-1-BTCUSDT-5")

    assert order == {
        "order_id": "991",
        "client_order_id": "wf-1-BTCUSDT-5",
        "status": "FILLED",
        "filled_qty": 0.01,
        "avg_price": 42050.0,
    }
    kwargs = client.post.call_args.kwargs
    assert kwargs["headers"] == {"X-MBX-APIKEY": "ak"}
    params = kwargs["params"]
    assert params["newClientOrderId"] == "wf-1-BTCUSDT-5"
    assert params["side"] == "BUY"
    assert params["type"] == "MARKET"
    assert "signature" in params and "timestamp" in params


async def test_get_positions_normalizes_open_position(client):
    client.get = AsyncMock(
        return_value=_json_response(
            [{"symbol": "BTCUSDT", "positionAmt": "0.01000000", "entryPrice": "42000.00"}]
        )
    )
    adapter = BinanceAdapter(client, CREDENTIALS, testnet=True)

    positions = await adapter.get_positions("BTCUSDT")

    assert positions == [
        {"symbol": "BTCUSDT", "side": "long", "entry_price": 42000.0, "quantity": 0.01}
    ]


async def test_get_positions_empty_when_flat(client):
    client.get = AsyncMock(
        return_value=_json_response(
            [{"symbol": "BTCUSDT", "positionAmt": "0.00000000", "entryPrice": "0.00"}]
        )
    )
    adapter = BinanceAdapter(client, CREDENTIALS, testnet=True)

    assert await adapter.get_positions("BTCUSDT") == []


async def test_cancel_order_normalizes_response(client):
    client.delete = AsyncMock(
        return_value=_json_response({"orderId": 991, "status": "CANCELED"})
    )
    adapter = BinanceAdapter(client, CREDENTIALS, testnet=True)

    result = await adapter.cancel_order("BTCUSDT", "991")

    assert result == {"order_id": "991", "status": "CANCELED"}
