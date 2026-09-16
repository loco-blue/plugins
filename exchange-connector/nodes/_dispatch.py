"""Exchange dispatch shared by all node wrappers.

The credential the operator picked for this node instance tells us which
exchange to hit (`context["auth"]["provider"]` is `"binance"` or `"okx"`).
`market_type` (`"spot"` or `"futures"`) is a plain input field on the nodes
where it matters - together the two pick one of 4 concrete adapter
classes. Nothing here branches on market_type beyond that one lookup;
`get_positions`/`set_leverage` always resolve `"futures"` since spot has
no such concept and those two nodes have no `market_type` input at all.
"""

from typing import Any

import httpx

from adapters.base import ExchangeAdapter, FuturesAdapter
from adapters.binance_futures import BinanceFuturesAdapter
from adapters.binance_spot import BinanceSpotAdapter
from adapters.okx_futures import OkxFuturesAdapter
from adapters.okx_spot import OkxSpotAdapter

_ADAPTERS: dict[tuple[str, str], type[ExchangeAdapter]] = {
    ("binance", "spot"): BinanceSpotAdapter,
    ("binance", "futures"): BinanceFuturesAdapter,
    ("okx", "spot"): OkxSpotAdapter,
    ("okx", "futures"): OkxFuturesAdapter,
}


def _resolve_exchange(
    context: dict[str, Any], market_type: str
) -> tuple[type[ExchangeAdapter], dict[str, Any]]:
    """Return the (adapter class, auth dict) pair for this node's credential."""
    auth = context.get("auth")
    if not auth:
        raise ValueError("exchange credentials required: context['auth'] is empty")
    provider = auth.get("provider")
    adapter_cls = _ADAPTERS.get((provider, market_type))
    if adapter_cls is None:
        if provider not in {"binance", "okx"}:
            raise ValueError(
                f"unrecognized exchange provider {provider!r}; expected one "
                "of ['binance', 'okx']"
            )
        raise ValueError(
            f"unsupported market_type {market_type!r}; expected 'spot' or 'futures'"
        )
    return adapter_cls, auth


async def run_get_klines(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    market_type = inputs.get("market_type", "spot")
    adapter_cls, auth = _resolve_exchange(context, market_type)
    testnet = inputs.get("testnet", True)
    async with httpx.AsyncClient() as client:
        adapter = adapter_cls(client, auth, testnet=testnet)
        klines = await adapter.get_klines(inputs["symbol"], inputs.get("interval", "1m"))
    return {"klines": klines}


async def run_place_order(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    market_type = inputs.get("market_type", "spot")
    adapter_cls, auth = _resolve_exchange(context, market_type)
    testnet = inputs.get("testnet", True)
    order_type = inputs.get("order_type", "market")
    stop_price = inputs.get("stop_price")
    reduce_only = inputs.get("reduce_only", False)
    leverage = inputs.get("leverage")

    is_futures = issubclass(adapter_cls, FuturesAdapter)
    futures_only_requested = order_type != "market" or reduce_only or leverage is not None
    if futures_only_requested and not is_futures:
        raise ValueError(
            "order_type != 'market', reduce_only=True, and leverage are only "
            "valid when market_type='futures'"
        )
    if order_type != "market" and stop_price is None:
        raise ValueError(f"order_type {order_type!r} requires stop_price")

    async with httpx.AsyncClient() as client:
        adapter = adapter_cls(client, auth, testnet=testnet)
        if leverage is not None:
            await adapter.set_leverage(inputs["symbol"], leverage)
        return await adapter.place_order(
            inputs["symbol"],
            inputs["side"],
            inputs["quantity"],
            inputs["client_order_id"],
            order_type=order_type,
            stop_price=stop_price,
            reduce_only=reduce_only,
        )


async def run_cancel_order(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    market_type = inputs.get("market_type", "spot")
    adapter_cls, auth = _resolve_exchange(context, market_type)
    testnet = inputs.get("testnet", True)
    async with httpx.AsyncClient() as client:
        adapter = adapter_cls(client, auth, testnet=testnet)
        return await adapter.cancel_order(inputs["symbol"], inputs["order_id"])


async def run_get_positions(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    adapter_cls, auth = _resolve_exchange(context, "futures")
    testnet = inputs.get("testnet", True)
    async with httpx.AsyncClient() as client:
        adapter = adapter_cls(client, auth, testnet=testnet)
        positions = await adapter.get_positions(inputs["symbol"])
    return {"positions": positions}


async def run_set_leverage(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    adapter_cls, auth = _resolve_exchange(context, "futures")
    testnet = inputs.get("testnet", True)
    async with httpx.AsyncClient() as client:
        adapter = adapter_cls(client, auth, testnet=testnet)
        return await adapter.set_leverage(inputs["symbol"], inputs["leverage"])


async def run_get_balance(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    market_type = inputs.get("market_type", "spot")
    adapter_cls, auth = _resolve_exchange(context, market_type)
    testnet = inputs.get("testnet", True)
    async with httpx.AsyncClient() as client:
        adapter = adapter_cls(client, auth, testnet=testnet)
        balances = await adapter.get_balance()
    return {"balances": balances}
