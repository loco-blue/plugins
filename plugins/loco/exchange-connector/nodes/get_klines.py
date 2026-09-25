from typing import Any

from loco_sdk import NodePlugin

from ._dispatch import run_get_klines


class GetKlinesNode(NodePlugin):
    """Fetch OHLCV candles from whichever exchange this node instance's
    connected credential belongs to."""

    async def execute(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return await run_get_klines(inputs, context)
