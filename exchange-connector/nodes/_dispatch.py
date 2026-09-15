"""Exchange dispatch shared by all 4 node wrappers.

The credential the operator picked for this node instance (Task 4's
docstring explains how) tells us which exchange to hit - `context["auth"]
["provider"]` is `"binance"` or `"okx"`. Everything else about the node is
identical between exchanges, which is exactly why this is one dispatch
function per operation instead of one function per (operation, exchange)
pair.
"""

from typing import Any

import httpx

from adapters.base import ExchangeAdapter
from adapters.binance import BinanceAdapter
from adapters.okx import OkxAdapter

_ADAPTERS: dict[str, type[ExchangeAdapter]] = {
    "binance": BinanceAdapter,
    "okx": OkxAdapter,
}


def _adapter_cls(context: dict[str, Any]) -> tuple[type[ExchangeAdapter], dict[str, Any]]:
    auth = context.get("auth")
    if not auth:
        raise ValueError("exchange credentials required: context['auth'] is empty")
    provider = auth.get("provider")
    adapter_cls = _ADAPTERS.get(provider)
    if adapter_cls is None:
        raise ValueError(
            f"unrecognized exchange provider {provider!r}; expected one of "
            f"{sorted(_ADAPTERS)}"
        )
    return adapter_cls, auth


async def run_get_klines(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    adapter_cls, auth = _adapter_cls(context)
    testnet = inputs.get("testnet", True)
    async with httpx.AsyncClient() as client:
        adapter = adapter_cls(client, auth, testnet=testnet)
        klines = await adapter.get_klines(inputs["symbol"], inputs.get("interval", "1m"))
    return {"klines": klines}


async def run_place_order(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    adapter_cls, auth = _adapter_cls(context)
    testnet = inputs.get("testnet", True)
    async with httpx.AsyncClient() as client:
        adapter = adapter_cls(client, auth, testnet=testnet)
        return await adapter.place_order(
            inputs["symbol"],
            inputs["side"],
            inputs["quantity"],
            inputs["client_order_id"],
        )


async def run_get_positions(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    adapter_cls, auth = _adapter_cls(context)
    testnet = inputs.get("testnet", True)
    async with httpx.AsyncClient() as client:
        adapter = adapter_cls(client, auth, testnet=testnet)
        positions = await adapter.get_positions(inputs["symbol"])
    return {"positions": positions}


async def run_cancel_order(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    adapter_cls, auth = _adapter_cls(context)
    testnet = inputs.get("testnet", True)
    async with httpx.AsyncClient() as client:
        adapter = adapter_cls(client, auth, testnet=testnet)
        return await adapter.cancel_order(inputs["symbol"], inputs["order_id"])
