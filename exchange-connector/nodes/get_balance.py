from typing import Any

from loco_sdk import NodePlugin

from ._dispatch import run_get_balance


class GetBalanceNode(NodePlugin):
    """Fetch account asset balances on whichever exchange this node
    instance's connected credential belongs to."""

    async def execute(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return await run_get_balance(inputs, context)
