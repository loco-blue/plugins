from typing import Any

from loco_sdk import NodePlugin

from ._dispatch import run_place_order


class PlaceOrderNode(NodePlugin):
    """Place a market order on whichever exchange this node instance's
    connected credential belongs to. `client_order_id` is the idempotency key."""

    async def execute(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return await run_place_order(inputs, context)
