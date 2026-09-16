"""Shared exchange-adapter contract.

Every adapter method returns the SAME shape regardless of which exchange
implements it - callers (the node wrappers in ../nodes/) never branch on
exchange after construction.

Normalized response contract:
    get_klines    -> [{open_time, open, high, low, close, volume}]
    place_order   -> {order_id, client_order_id, status, filled_qty, avg_price}
    cancel_order  -> {order_id, status}
    get_balance   -> [{asset, free, locked}]
    get_positions -> [{symbol, side, entry_price, quantity}]     (FuturesAdapter only)
    set_leverage  -> {symbol, leverage, status}                   (FuturesAdapter only)
"""

from abc import ABC, abstractmethod
from typing import Any


class ExchangeAdapter(ABC):
    """Normalizes one exchange's REST API into the shared response contract.

    Common to both spot and futures markets. Which concrete subclass
    `nodes/_dispatch.py` instantiates is what decides spot vs futures - no
    method here takes a `market_type` parameter, and none branches on it.
    """

    def __init__(
        self,
        client: Any,
        credentials: dict[str, Any],
        testnet: bool = True,
    ) -> None:
        self.client = client
        self.credentials = credentials
        self.testnet = testnet

    @abstractmethod
    async def get_klines(
        self, symbol: str, interval: str
    ) -> list[dict[str, Any]]:
        """Return recent candlesticks, oldest first."""

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        client_order_id: str,
        order_type: str = "market",
        stop_price: float | None = None,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """Place an order; `client_order_id` is the idempotency key.

        `order_type` is one of "market", "stop_market", "take_profit_market".
        `stop_price` is required when `order_type != "market"`. `reduce_only`
        only makes sense against an existing leveraged position; a spot
        implementation must reject `reduce_only=True` rather than silently
        ignore it.

        `leverage` is deliberately NOT a parameter here: setting leverage is
        its own exchange API call on both Binance and OKX, so
        `nodes/_dispatch.py` calls `FuturesAdapter.set_leverage` itself,
        before this method, when the caller supplied one.
        """

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Cancel a resting order."""

    @abstractmethod
    async def get_balance(self) -> list[dict[str, Any]]:
        """Return this account's non-zero asset balances.

        `locked` means "not available for placing a new order right now" -
        but what counts toward that varies by adapter: on Binance Spot and
        OKX it is funds held by resting orders (plus, on OKX, margin frozen
        by the account). On Binance Futures, `locked` is computed as
        `max(total - free, 0.0)`, which also includes margin already
        committed to open positions - a different, broader concept than a
        resting order's hold on spot/OKX.
        """


class FuturesAdapter(ExchangeAdapter):
    """Adds the operations that only make sense on a leveraged position.

    No spot adapter subclasses this - there is nothing to runtime-guard
    inside these methods, because a spot adapter has no `get_positions`/
    `set_leverage` to call at all. The one guard this design needs
    (rejecting `place_order`'s futures-only fields when the resolved
    adapter is NOT a `FuturesAdapter`) lives in `nodes/_dispatch.py`, the
    one place that knows both which concrete class was resolved and what
    the caller asked for.
    """

    @abstractmethod
    async def get_positions(self, symbol: str) -> list[dict[str, Any]]:
        """Return open positions for `symbol` (empty list if flat)."""

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        """Set leverage for `symbol`. Called once per `place_order` that
        supplies a `leverage` value - see `nodes/_dispatch.py`."""
