"""Cross-adapter contract test.

Both adapters must normalize to the SAME dict shape (adapters/base.py), so
future drift on one exchange is caught here rather than in a caller.

`place_order` is deliberately excluded: OKX's place-order response is an
acknowledgement with no fill data, so its `status`/`filled_qty`/`avg_price`
semantics are legitimately asymmetric with Binance's (see README's "Known
simplifications").
"""

from unittest.mock import AsyncMock, MagicMock

from adapters.binance import BinanceAdapter
from adapters.okx import OkxAdapter

BINANCE_CREDENTIALS = {"auth_type": "api_key", "api_key": "ak", "api_secret": "as"}
OKX_CREDENTIALS = {
    "auth_type": "api_key",
    "api_key": "ak",
    "api_secret": "as",
    "api_passphrase": "pp",
}


def _json_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def _binance(get=None, post=None, delete=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=_json_response(get))
    client.post = AsyncMock(return_value=_json_response(post))
    client.delete = AsyncMock(return_value=_json_response(delete))
    return BinanceAdapter(client, BINANCE_CREDENTIALS, testnet=True)


def _okx(get=None, post=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=_json_response(get))
    client.post = AsyncMock(return_value=_json_response(post))
    return OkxAdapter(client, OKX_CREDENTIALS, testnet=True)


async def test_get_klines_shape_is_identical_across_adapters():
    binance = await _binance(
        get=[
            [1700000000000, "1", "2", "0.5", "1.5", "10",
             1700000059999, "0", 0, "0", "0", "0"]
        ]
    ).get_klines("BTCUSDT", "1m")
    okx = await _okx(
        get={
            "code": "0",
            "data": [["1700000000000", "1", "2", "0.5", "1.5", "10", "x", "x", "x"]],
        }
    ).get_klines("BTC-USDT", "1m")

    assert binance and okx
    assert set(binance[0]) == set(okx[0])


async def test_get_positions_shape_is_identical_across_adapters():
    binance = await _binance(
        get=[{"symbol": "BTCUSDT", "positionAmt": "0.01", "entryPrice": "42000.0"}]
    ).get_positions("BTCUSDT")
    okx = await _okx(
        get={
            "code": "0",
            "data": [
                {
                    "instId": "BTC-USDT",
                    "posSide": "long",
                    "avgPx": "42000.0",
                    "pos": "0.01",
                }
            ],
        }
    ).get_positions("BTC-USDT")

    assert binance and okx
    assert set(binance[0]) == set(okx[0])


async def test_cancel_order_shape_is_identical_across_adapters():
    binance = await _binance(
        delete={"orderId": 991, "status": "CANCELED"}
    ).cancel_order("BTCUSDT", "991")
    okx = await _okx(
        post={"code": "0", "data": [{"ordId": "ord-1", "sCode": "0"}]}
    ).cancel_order("BTC-USDT", "ord-1")

    assert set(binance) == set(okx)
