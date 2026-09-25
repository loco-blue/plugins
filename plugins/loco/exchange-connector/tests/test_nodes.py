from unittest.mock import AsyncMock, patch

import pytest

from nodes.cancel_order import CancelOrderNode
from nodes.get_balance import GetBalanceNode
from nodes.get_klines import GetKlinesNode
from nodes.get_positions import GetPositionsNode
from nodes.place_order import PlaceOrderNode
from nodes.set_leverage import SetLeverageNode

AUTH_BINANCE = {
    "auth_type": "api_key",
    "provider": "binance",
    "api_key": "ak",
    "api_secret": "as",
}
AUTH_OKX = {
    "auth_type": "api_key",
    "provider": "okx",
    "api_key": "ak",
    "api_secret": "as",
    "api_passphrase": "pp",
}


async def test_get_klines_dispatches_to_binance_spot_by_default():
    with patch(
        "nodes._dispatch.BinanceSpotAdapter.get_klines",
        new=AsyncMock(return_value=[{"open_time": "1", "open": 1.0, "high": 1.0,
                                      "low": 1.0, "close": 1.0, "volume": 1.0}]),
    ) as mocked:
        node = GetKlinesNode()
        result = await node.execute(
            {"symbol": "BTCUSDT", "interval": "1m", "testnet": True},
            {"auth": AUTH_BINANCE},
        )
    assert result == {
        "klines": [
            {"open_time": "1", "open": 1.0, "high": 1.0, "low": 1.0,
             "close": 1.0, "volume": 1.0}
        ]
    }
    mocked.assert_awaited_once_with("BTCUSDT", "1m")


async def test_get_klines_dispatches_to_okx_futures_when_asked():
    with patch(
        "nodes._dispatch.OkxFuturesAdapter.get_klines",
        new=AsyncMock(return_value=[]),
    ) as mocked:
        node = GetKlinesNode()
        await node.execute(
            {"symbol": "BTC-USDT-SWAP", "market_type": "futures", "testnet": True},
            {"auth": AUTH_OKX},
        )
    mocked.assert_awaited_once()


async def test_place_order_market_spot_does_not_call_set_leverage():
    with (
        patch(
            "nodes._dispatch.BinanceSpotAdapter.place_order",
            new=AsyncMock(return_value={"order_id": "1", "client_order_id": "wf-1",
                                          "status": "FILLED", "filled_qty": 0.01,
                                          "avg_price": 42000.0}),
        ) as mock_place,
    ):
        node = PlaceOrderNode()
        result = await node.execute(
            {"symbol": "BTCUSDT", "side": "buy", "quantity": 0.01,
             "client_order_id": "wf-1", "testnet": True},
            {"auth": AUTH_BINANCE},
        )
    assert result["order_id"] == "1"
    mock_place.assert_awaited_once_with(
        "BTCUSDT", "buy", 0.01, "wf-1", order_type="market", stop_price=None, reduce_only=False
    )


async def test_place_order_futures_with_leverage_calls_set_leverage_first():
    calls = []

    async def fake_set_leverage(self, symbol, leverage):
        calls.append(("set_leverage", symbol, leverage))
        return {"symbol": symbol, "leverage": leverage, "status": "ok"}

    async def fake_place_order(self, *args, **kwargs):
        calls.append(("place_order", args, kwargs))
        return {"order_id": "1", "client_order_id": "wf-1", "status": "NEW",
                "filled_qty": 0.0, "avg_price": 0.0}

    with (
        patch("nodes._dispatch.BinanceFuturesAdapter.set_leverage", new=fake_set_leverage),
        patch("nodes._dispatch.BinanceFuturesAdapter.place_order", new=fake_place_order),
    ):
        node = PlaceOrderNode()
        await node.execute(
            {"symbol": "BTCUSDT", "market_type": "futures", "side": "buy",
             "quantity": 0.01, "client_order_id": "wf-1", "leverage": 10, "testnet": True},
            {"auth": AUTH_BINANCE},
        )

    assert calls[0] == ("set_leverage", "BTCUSDT", 10)
    assert calls[1][0] == "place_order"


async def test_place_order_rejects_leverage_on_spot_before_any_network_call():
    with patch(
        "nodes._dispatch.BinanceSpotAdapter.place_order", new=AsyncMock()
    ) as mock_place:
        node = PlaceOrderNode()
        with pytest.raises(ValueError, match="futures"):
            await node.execute(
                {"symbol": "BTCUSDT", "side": "buy", "quantity": 0.01,
                 "client_order_id": "wf-1", "leverage": 10, "testnet": True},
                {"auth": AUTH_BINANCE},
            )
    mock_place.assert_not_awaited()


async def test_place_order_rejects_reduce_only_on_spot_before_any_network_call():
    with patch(
        "nodes._dispatch.BinanceSpotAdapter.place_order", new=AsyncMock()
    ) as mock_place:
        node = PlaceOrderNode()
        with pytest.raises(ValueError, match="futures"):
            await node.execute(
                {"symbol": "BTCUSDT", "side": "buy", "quantity": 0.01,
                 "client_order_id": "wf-1", "reduce_only": True, "testnet": True},
                {"auth": AUTH_BINANCE},
            )
    mock_place.assert_not_awaited()


async def test_place_order_rejects_stop_order_without_stop_price():
    node = PlaceOrderNode()
    with pytest.raises(ValueError, match="stop_price"):
        await node.execute(
            {"symbol": "BTCUSDT", "market_type": "futures", "side": "buy",
             "quantity": 0.01, "client_order_id": "wf-1",
             "order_type": "stop_market", "testnet": True},
            {"auth": AUTH_BINANCE},
        )


async def test_get_positions_always_resolves_futures_even_with_no_market_type_input():
    with patch(
        "nodes._dispatch.BinanceFuturesAdapter.get_positions",
        new=AsyncMock(return_value=[]),
    ) as mocked:
        node = GetPositionsNode()
        await node.execute({"symbol": "BTCUSDT", "testnet": True}, {"auth": AUTH_BINANCE})
    mocked.assert_awaited_once_with("BTCUSDT")


async def test_set_leverage_dispatches_to_okx_futures():
    with patch(
        "nodes._dispatch.OkxFuturesAdapter.set_leverage",
        new=AsyncMock(return_value={"symbol": "BTC-USDT-SWAP", "leverage": 5, "status": "ok"}),
    ) as mocked:
        node = SetLeverageNode()
        result = await node.execute(
            {"symbol": "BTC-USDT-SWAP", "leverage": 5, "testnet": True}, {"auth": AUTH_OKX}
        )
    assert result == {"symbol": "BTC-USDT-SWAP", "leverage": 5, "status": "ok"}
    mocked.assert_awaited_once_with("BTC-USDT-SWAP", 5)


async def test_get_balance_dispatches_with_market_type():
    with patch(
        "nodes._dispatch.OkxFuturesAdapter.get_balance",
        new=AsyncMock(return_value=[{"asset": "USDT", "free": 1.0, "locked": 0.0}]),
    ) as mocked:
        node = GetBalanceNode()
        result = await node.execute(
            {"market_type": "futures", "testnet": True}, {"auth": AUTH_OKX}
        )
    assert result == {"balances": [{"asset": "USDT", "free": 1.0, "locked": 0.0}]}
    mocked.assert_awaited_once_with()


async def test_cancel_order_dispatches_to_okx_spot_by_default():
    with patch(
        "nodes._dispatch.OkxSpotAdapter.cancel_order",
        new=AsyncMock(return_value={"order_id": "ord-1", "status": "canceled"}),
    ) as mocked:
        node = CancelOrderNode()
        result = await node.execute(
            {"symbol": "BTC-USDT", "order_id": "ord-1", "testnet": True}, {"auth": AUTH_OKX}
        )
    assert result == {"order_id": "ord-1", "status": "canceled"}
    mocked.assert_awaited_once_with("BTC-USDT", "ord-1")


async def test_missing_auth_raises_before_any_network_call():
    node = GetKlinesNode()
    with pytest.raises(ValueError, match="auth"):
        await node.execute({"symbol": "BTCUSDT", "interval": "1m"}, {})


async def test_an_unrecognized_provider_is_rejected_before_any_network_call():
    node = GetKlinesNode()
    with pytest.raises(ValueError, match="provider"):
        await node.execute(
            {"symbol": "BTCUSDT", "interval": "1m"},
            {"auth": {"provider": "kraken", "api_key": "ak", "api_secret": "as"}},
        )


async def test_an_unrecognized_market_type_is_rejected_before_any_network_call():
    node = GetKlinesNode()
    with pytest.raises(ValueError, match="market_type"):
        await node.execute(
            {"symbol": "BTCUSDT", "interval": "1m", "market_type": "margin"},
            {"auth": AUTH_BINANCE},
        )
