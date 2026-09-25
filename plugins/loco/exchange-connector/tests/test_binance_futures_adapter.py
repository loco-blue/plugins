from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.binance_futures import BinanceFuturesAdapter

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


async def test_get_klines_hits_the_futures_testnet_host(client):
    raw = [[1700000000000, "1", "2", "0.5", "1.5", "10", 0, "0", 0, "0", "0", "0"]]
    client.get = AsyncMock(return_value=_json_response(raw))
    adapter = BinanceFuturesAdapter(client, CREDENTIALS, testnet=True)

    klines = await adapter.get_klines("BTCUSDT", "1m")

    assert klines[0]["open_time"] == "1700000000000"
    assert client.get.call_args.args[0] == "https://testnet.binancefuture.com/fapi/v1/klines"


async def test_place_order_market_normalizes_response(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {
                "orderId": 5001,
                "clientOrderId": "wf-1-BTCUSDT-5",
                "status": "NEW",
                "executedQty": "0",
                "avgPrice": "0",
            }
        )
    )
    adapter = BinanceFuturesAdapter(client, CREDENTIALS, testnet=True)

    order = await adapter.place_order("BTCUSDT", "buy", 0.01, "wf-1-BTCUSDT-5")

    assert order == {
        "order_id": "5001",
        "client_order_id": "wf-1-BTCUSDT-5",
        "status": "NEW",
        "filled_qty": 0.0,
        "avg_price": 0.0,
    }
    params = client.post.call_args.kwargs["params"]
    assert params["type"] == "MARKET"
    assert params["reduceOnly"] == "false"
    assert "stopPrice" not in params


async def test_place_order_stop_market_includes_stop_price_and_reduce_only(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {"orderId": 5002, "clientOrderId": "wf-1", "status": "NEW",
             "executedQty": "0", "avgPrice": "0"}
        )
    )
    adapter = BinanceFuturesAdapter(client, CREDENTIALS, testnet=True)

    await adapter.place_order(
        "BTCUSDT", "sell", 0.01, "wf-1",
        order_type="stop_market", stop_price=39000.0, reduce_only=True,
    )

    params = client.post.call_args.kwargs["params"]
    assert params["type"] == "STOP_MARKET"
    assert params["stopPrice"] == 39000.0
    assert params["reduceOnly"] == "true"


async def test_place_order_requires_stop_price_for_non_market_type(client):
    adapter = BinanceFuturesAdapter(client, CREDENTIALS, testnet=True)
    with pytest.raises(ValueError, match="stop_price"):
        await adapter.place_order("BTCUSDT", "sell", 0.01, "wf-1", order_type="stop_market")


async def test_get_positions_filters_flat_and_normalizes_open(client):
    client.get = AsyncMock(
        return_value=_json_response(
            [
                {"symbol": "BTCUSDT", "positionAmt": "0.01", "entryPrice": "42000.0"},
                {"symbol": "ETHUSDT", "positionAmt": "0.00", "entryPrice": "0.0"},
            ]
        )
    )
    adapter = BinanceFuturesAdapter(client, CREDENTIALS, testnet=True)

    positions = await adapter.get_positions("BTCUSDT")

    assert positions == [
        {"symbol": "BTCUSDT", "side": "long", "entry_price": 42000.0, "quantity": 0.01}
    ]


async def test_set_leverage_normalizes_response(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {"symbol": "BTCUSDT", "leverage": 10, "maxNotionalValue": "1000000"}
        )
    )
    adapter = BinanceFuturesAdapter(client, CREDENTIALS, testnet=True)

    result = await adapter.set_leverage("BTCUSDT", 10)

    assert result == {"symbol": "BTCUSDT", "leverage": 10, "status": "ok"}


async def test_get_balance_normalizes_and_filters_zero(client):
    client.get = AsyncMock(
        return_value=_json_response(
            [
                {"asset": "USDT", "balance": "1000.0", "availableBalance": "800.0"},
                {"asset": "BUSD", "balance": "0.0", "availableBalance": "0.0"},
            ]
        )
    )
    adapter = BinanceFuturesAdapter(client, CREDENTIALS, testnet=True)

    balances = await adapter.get_balance()

    assert balances == [{"asset": "USDT", "free": 800.0, "locked": 200.0}]
