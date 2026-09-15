"""Shared exchange-adapter contract.

Every adapter method returns the SAME shape regardless of which exchange
implements it - callers (the node wrappers in ../nodes/) never branch on
exchange after construction.

Normalized response contract:
    get_klines    -> [{open_time, open, high, low, close, volume}]
    place_order   -> {order_id, client_order_id, status, filled_qty, avg_price}
    get_positions -> [{symbol, side, entry_price, quantity}]
    cancel_order  -> {order_id, status}
"""

from abc import ABC, abstractmethod
from typing import Any


class ExchangeAdapter(ABC):
    """Normalizes one exchange's REST API into the shared response contract.

    `credentials` is the raw `context["auth"]` dict handed to the node's
    `execute()` by the sandbox - see Task 4's open verification item about
    which fields it actually contains.
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
        self, symbol: str, side: str, quantity: float, client_order_id: str
    ) -> dict[str, Any]:
        """Place a market order; `client_order_id` is the idempotency key."""

    @abstractmethod
    async def get_positions(self, symbol: str) -> list[dict[str, Any]]:
        """Return open positions for `symbol` (empty list if flat)."""

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Cancel a resting order."""
