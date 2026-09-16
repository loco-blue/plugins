from typing import Any

from loco_sdk import NodePlugin

from ._dispatch import run_set_leverage


class SetLeverageNode(NodePlugin):
    """Set leverage for a symbol on whichever exchange this node instance's
    connected credential belongs to. Futures only."""

    async def execute(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return await run_set_leverage(inputs, context)
