"""Cross-adapter contract test.

All adapters must normalize to the SAME dict shape per operation
(adapters/base.py), so future drift on one exchange/market is caught here
rather than in a caller.

`place_order` is deliberately excluded: OKX's place-order response is an
acknowledgement with no fill data, so its `status`/`filled_qty`/`avg_price`
semantics are legitimately asymmetric with Binance's (see README's "Known
simplifications"). `get_positions`/`set_leverage` parity across the two
FUTURES adapters is added in a later task, once both futures classes exist.
"""

from unittest.mock import AsyncMock, MagicMock

from adapters.binance_futures import BinanceFuturesAdapter
from adapters.binance_spot import BinanceSpotAdapter
from adapters.okx_futures import OkxFuturesAdapter
from adapters.okx_spot import OkxSpotAdapter

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


def _binance_spot(get=None, post=None, delete=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=_json_response(get))
    client.post = AsyncMock(return_value=_json_response(post))
    client.delete = AsyncMock(return_value=_json_response(delete))
    return BinanceSpotAdapter(client, BINANCE_CREDENTIALS, testnet=True)


def _okx_spot(get=None, post=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=_json_response(get))
    client.post = AsyncMock(return_value=_json_response(post))
    return OkxSpotAdapter(client, OKX_CREDENTIALS, testnet=True)


async def test_get_klines_shape_is_identical_across_spot_adapters():
    binance = await _binance_spot(
        get=[
            [1700000000000, "1", "2", "0.5", "1.5", "10",
             1700000059999, "0", 0, "0", "0", "0"]
        ]
    ).get_klines("BTCUSDT", "1m")
    okx = await _okx_spot(
        get={
            "code": "0",
            "data": [["1700000000000", "1", "2", "0.5", "1.5", "10", "x", "x", "x"]],
        }
    ).get_klines("BTC-USDT", "1m")

    assert binance and okx
    assert set(binance[0]) == set(okx[0])


async def test_cancel_order_shape_is_identical_across_spot_adapters():
    binance = await _binance_spot(
        delete={"orderId": 991, "status": "CANCELED"}
    ).cancel_order("BTCUSDT", "991")
    okx = await _okx_spot(
        post={"code": "0", "data": [{"ordId": "ord-1", "sCode": "0"}]}
    ).cancel_order("BTC-USDT", "ord-1")

    assert set(binance) == set(okx)


async def test_get_balance_shape_is_identical_across_spot_adapters():
    binance = await _binance_spot(
        get={"balances": [{"asset": "USDT", "free": "1", "locked": "0"}]}
    ).get_balance()
    okx = await _okx_spot(
        get={"code": "0", "data": [{"details": [{"ccy": "USDT", "availBal": "1", "frozenBal": "0"}]}]}
    ).get_balance()

    assert binance and okx
    assert set(binance[0]) == set(okx[0])


BINANCE_CREDENTIALS_FUTURES = BINANCE_CREDENTIALS  # same shape, reused
OKX_CREDENTIALS_FUTURES = OKX_CREDENTIALS


def _binance_futures(get=None, post=None, delete=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=_json_response(get))
    client.post = AsyncMock(return_value=_json_response(post))
    client.delete = AsyncMock(return_value=_json_response(delete))
    return BinanceFuturesAdapter(client, BINANCE_CREDENTIALS_FUTURES, testnet=True)


def _okx_futures(get=None, post=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=_json_response(get))
    client.post = AsyncMock(return_value=_json_response(post))
    return OkxFuturesAdapter(client, OKX_CREDENTIALS_FUTURES, testnet=True)


async def test_get_positions_shape_is_identical_across_futures_adapters():
    binance = await _binance_futures(
        get=[{"symbol": "BTCUSDT", "positionAmt": "0.01", "entryPrice": "42000.0"}]
    ).get_positions("BTCUSDT")
    okx = await _okx_futures(
        get={
            "code": "0",
            "data": [
                {"instId": "BTC-USDT-SWAP", "posSide": "long", "avgPx": "42000.0", "pos": "1"}
            ],
        }
    ).get_positions("BTC-USDT-SWAP")

    assert binance and okx
    assert set(binance[0]) == set(okx[0])


async def test_set_leverage_shape_is_identical_across_futures_adapters():
    binance = await _binance_futures(
        post={"symbol": "BTCUSDT", "leverage": 10, "maxNotionalValue": "1000000"}
    ).set_leverage("BTCUSDT", 10)
    okx = await _okx_futures(
        post={"code": "0", "data": [{"instId": "BTC-USDT-SWAP", "lever": "10", "mgnMode": "cross"}]}
    ).set_leverage("BTC-USDT-SWAP", 10)

    assert set(binance) == set(okx)


async def test_get_klines_shape_is_identical_across_all_four_adapters():
    binance_spot = await _binance_spot(
        get=[[1700000000000, "1", "2", "0.5", "1.5", "10",
              1700000059999, "0", 0, "0", "0", "0"]]
    ).get_klines("BTCUSDT", "1m")
    binance_futures = await _binance_futures(
        get=[[1700000000000, "1", "2", "0.5", "1.5", "10",
              1700000059999, "0", 0, "0", "0", "0"]]
    ).get_klines("BTCUSDT", "1m")
    okx_spot = await _okx_spot(
        get={"code": "0", "data": [["1700000000000", "1", "2", "0.5", "1.5", "10", "x", "x", "x"]]}
    ).get_klines("BTC-USDT", "1m")
    okx_futures = await _okx_futures(
        get={"code": "0", "data": [["1700000000000", "1", "2", "0.5", "1.5", "10", "x", "x", "x"]]}
    ).get_klines("BTC-USDT-SWAP", "1m")

    shapes = [set(a[0]) for a in (binance_spot, binance_futures, okx_spot, okx_futures)]
    assert all(shape == shapes[0] for shape in shapes)
