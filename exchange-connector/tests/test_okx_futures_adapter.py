from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.okx_futures import OkxFuturesAdapter

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


async def test_get_klines_normalizes_and_reverses(client):
    raw = {
        "code": "0",
        "data": [
            ["1700000060000", "1", "2", "0.5", "1.5", "2.0", "x", "x", "x"],
            ["1700000000000", "0.9", "1.1", "0.8", "1.0", "1.0", "x", "x", "x"],
        ],
    }
    client.get = AsyncMock(return_value=_json_response(raw))
    adapter = OkxFuturesAdapter(client, CREDENTIALS, testnet=True)

    klines = await adapter.get_klines("BTC-USDT-SWAP", "1m")

    assert [k["open_time"] for k in klines] == ["1700000000000", "1700000060000"]


async def test_place_order_market_sends_cross_margin_mode(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {"code": "0", "data": [{"ordId": "ord-1", "clOrdId": "wf-1", "sCode": "0", "sMsg": ""}]}
        )
    )
    adapter = OkxFuturesAdapter(client, CREDENTIALS, testnet=True)

    order = await adapter.place_order("BTC-USDT-SWAP", "buy", 1, "wf-1")

    assert order == {
        "order_id": "ord-1",
        "client_order_id": "wf-1",
        "status": "live",
        "filled_qty": 0.0,
        "avg_price": 0.0,
    }
    sent_body = client.post.call_args.kwargs["content"].decode("utf-8")
    assert '"tdMode": "cross"' in sent_body
    assert '"ordType": "market"' in sent_body


async def test_place_order_stop_market_sends_conditional_with_trigger_price(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {"code": "0", "data": [{"ordId": "ord-2", "clOrdId": "wf-2", "sCode": "0", "sMsg": ""}]}
        )
    )
    adapter = OkxFuturesAdapter(client, CREDENTIALS, testnet=True)

    await adapter.place_order(
        "BTC-USDT-SWAP", "sell", 1, "wf-2",
        order_type="stop_market", stop_price=39000.0, reduce_only=True,
    )

    sent_body = client.post.call_args.kwargs["content"].decode("utf-8")
    assert '"ordType": "conditional"' in sent_body
    assert '"slTriggerPx": "39000.0"' in sent_body
    assert '"reduceOnly": true' in sent_body


async def test_place_order_requires_stop_price_for_non_market_type(client):
    adapter = OkxFuturesAdapter(client, CREDENTIALS, testnet=True)
    with pytest.raises(ValueError, match="stop_price"):
        await adapter.place_order("BTC-USDT-SWAP", "sell", 1, "wf-1", order_type="stop_market")


async def test_get_positions_normalizes_open_position(client):
    client.get = AsyncMock(
        return_value=_json_response(
            {
                "code": "0",
                "data": [
                    {"instId": "BTC-USDT-SWAP", "posSide": "net", "avgPx": "42000.0", "pos": "1"}
                ],
            }
        )
    )
    adapter = OkxFuturesAdapter(client, CREDENTIALS, testnet=True)

    positions = await adapter.get_positions("BTC-USDT-SWAP")

    assert positions == [
        {"symbol": "BTC-USDT-SWAP", "side": "long", "entry_price": 42000.0, "quantity": 1.0}
    ]


async def test_get_positions_normalizes_short_position(client):
    client.get = AsyncMock(
        return_value=_json_response(
            {
                "code": "0",
                "data": [
                    {"instId": "BTC-USDT-SWAP", "posSide": "net", "avgPx": "42000.0", "pos": "-1"}
                ],
            }
        )
    )
    adapter = OkxFuturesAdapter(client, CREDENTIALS, testnet=True)

    positions = await adapter.get_positions("BTC-USDT-SWAP")

    assert positions == [
        {"symbol": "BTC-USDT-SWAP", "side": "short", "entry_price": 42000.0, "quantity": 1.0}
    ]


async def test_set_leverage_normalizes_response(client):
    client.post = AsyncMock(
        return_value=_json_response(
            {"code": "0", "data": [{"instId": "BTC-USDT-SWAP", "lever": "10", "mgnMode": "cross"}]}
        )
    )
    adapter = OkxFuturesAdapter(client, CREDENTIALS, testnet=True)

    result = await adapter.set_leverage("BTC-USDT-SWAP", 10)

    assert result == {"symbol": "BTC-USDT-SWAP", "leverage": 10, "status": "ok"}


async def test_get_balance_normalizes_and_filters_zero(client):
    client.get = AsyncMock(
        return_value=_json_response(
            {
                "code": "0",
                "data": [
                    {
                        "details": [
                            {"ccy": "USDT", "availBal": "500.0", "frozenBal": "10.0"},
                            {"ccy": "ETH", "availBal": "0", "frozenBal": "0"},
                        ]
                    }
                ],
            }
        )
    )
    adapter = OkxFuturesAdapter(client, CREDENTIALS, testnet=True)

    balances = await adapter.get_balance()

    assert balances == [{"asset": "USDT", "free": 500.0, "locked": 10.0}]
