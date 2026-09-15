from unittest.mock import AsyncMock, patch

import pytest

from nodes.cancel_order import CancelOrderNode
from nodes.get_klines import GetKlinesNode
from nodes.get_positions import GetPositionsNode
from nodes.place_order import PlaceOrderNode

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


async def test_get_klines_dispatches_to_binance_when_the_credential_is_binance():
    with patch(
        "nodes._dispatch.BinanceAdapter.get_klines",
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


async def test_place_order_dispatches_to_okx_when_the_credential_is_okx():
    with patch(
        "nodes._dispatch.OkxAdapter.place_order",
        new=AsyncMock(
            return_value={
                "order_id": "1",
                "client_order_id": "wf-1-BTC-USDT-5",
                "status": "filled",
                "filled_qty": 0.01,
                "avg_price": 42000.0,
            }
        ),
    ) as mocked:
        node = PlaceOrderNode()
        result = await node.execute(
            {
                "symbol": "BTC-USDT",
                "side": "buy",
                "quantity": 0.01,
                "client_order_id": "wf-1-BTC-USDT-5",
                "testnet": True,
            },
            {"auth": AUTH_OKX},
        )
    assert result["client_order_id"] == "wf-1-BTC-USDT-5"
    mocked.assert_awaited_once_with("BTC-USDT", "buy", 0.01, "wf-1-BTC-USDT-5")


async def test_get_positions_dispatches_to_binance_when_the_credential_is_binance():
    with patch(
        "nodes._dispatch.BinanceAdapter.get_positions",
        new=AsyncMock(
            return_value=[
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 42000.0,
                    "quantity": 0.01,
                }
            ]
        ),
    ) as mocked:
        node = GetPositionsNode()
        result = await node.execute(
            {"symbol": "BTCUSDT", "testnet": True},
            {"auth": AUTH_BINANCE},
        )
    assert result == {
        "positions": [
            {
                "symbol": "BTCUSDT",
                "side": "long",
                "entry_price": 42000.0,
                "quantity": 0.01,
            }
        ]
    }
    mocked.assert_awaited_once_with("BTCUSDT")


async def test_cancel_order_dispatches_to_okx_when_the_credential_is_okx():
    with patch(
        "nodes._dispatch.OkxAdapter.cancel_order",
        new=AsyncMock(return_value={"order_id": "ord-1", "status": "canceled"}),
    ) as mocked:
        node = CancelOrderNode()
        result = await node.execute(
            {"symbol": "BTC-USDT", "order_id": "ord-1", "testnet": True},
            {"auth": AUTH_OKX},
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
