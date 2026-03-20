"""
Flag Message - Gmail API Node

Star/unstar messages for follow-up
"""

from typing import Any
import logging

import httpx
from loco_sdk import NodePlugin, AuthContext

logger = logging.getLogger(__name__)


class FlagMessageNode(NodePlugin):
    """Star or unstar Gmail messages"""

    async def execute(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Star or unstar a Gmail message.

        Args:
            inputs: Input values:
                - message_id: Gmail message ID
                - action: 'star' or 'unstar'
            context: Workflow execution context with auth credentials.

        Returns:
            Output values:
                - message_id: Message ID
                - labels: Updated label IDs
                - status: Operation status
        """
        # Get auth context and wrap with AuthContext helper
        auth_data = context.get("auth")
        if not auth_data:
            raise ValueError(
                "OAuth authentication required. Please authorize Gmail access."
            )

        auth = AuthContext(auth_data)

        message_id = inputs.get("message_id")
        if not message_id:
            raise ValueError("Missing required input: message_id")

        action = inputs.get("action", "star").lower()
        if action not in ["star", "unstar"]:
            raise ValueError("Action must be 'star' or 'unstar'")

        logger.info(f"{action.capitalize()}ring message: {message_id}")

        headers = auth.get_header()
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient() as client:
            url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify"

            # Build request body
            if action == "star":
                body = {"addLabelIds": ["STARRED"]}
            else:
                body = {"removeLabelIds": ["STARRED"]}

            response = await client.post(
                url,
                headers=headers,
                json=body,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

        return {
            "message_id": result.get("id"),
            "labels": result.get("labelIds", []),
            "status": f"{action}red",
        }
