from typing import Any

from loco_sdk import NodePlugin

from ._dispatch import run_cancel_order


class CancelOrderNode(NodePlugin):
    """Cancel a resting order on whichever exchange this node instance's
    connected credential belongs to."""

    async def execute(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return await run_cancel_order(inputs, context)
