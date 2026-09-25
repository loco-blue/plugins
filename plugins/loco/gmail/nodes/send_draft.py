"""
Send Draft - Gmail API Node

Send an existing draft email
"""

from typing import Any
import logging

import httpx
from loco_sdk import NodePlugin, AuthContext

logger = logging.getLogger(__name__)


class SendDraftNode(NodePlugin):
    """Send an existing draft email"""

    async def execute(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Send an existing draft email.

        Args:
            inputs: Input values:
                - draft_id: Gmail draft ID (or message_id)
            context: Workflow execution context with auth credentials.

        Returns:
            Output values:
                - message_id: Sent message ID
                - thread_id: Thread ID
                - status: Send status
        """
        # Get auth context and wrap with AuthContext helper
        auth_data = context.get("auth")
        if not auth_data:
            raise ValueError(
                "OAuth authentication required. Please authorize Gmail access."
            )

        auth = AuthContext(auth_data)

        draft_id = inputs.get("draft_id")
        if not draft_id:
            raise ValueError("Missing required input: draft_id")

        logger.info(f"Sending draft: {draft_id}")

        headers = auth.get_header()
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient() as client:
            # Try to get draft first to verify it exists
            get_url = f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}"
            try:
                get_response = await client.get(
                    get_url,
                    headers=auth.get_header(),
                    timeout=30.0,
                )
                get_response.raise_for_status()
                draft_data = get_response.json()
                actual_draft_id = draft_data.get("id")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Might be message_id instead of draft_id, try to find draft
                    list_url = (
                        "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
                    )
                    list_response = await client.get(
                        list_url,
                        headers=auth.get_header(),
                        timeout=30.0,
                    )
                    list_response.raise_for_status()
                    drafts = list_response.json().get("drafts", [])

                    actual_draft_id = None
                    for draft in drafts:
                        if draft.get("message", {}).get("id") == draft_id:
                            actual_draft_id = draft.get("id")
                            break

                    if not actual_draft_id:
                        raise ValueError(f"Draft not found: {draft_id}")
                else:
                    raise

            # Send draft
            send_url = (
                "https://gmail.googleapis.com/gmail/v1/users/me/drafts/send"
            )
            response = await client.post(
                send_url,
                headers=headers,
                json={"id": actual_draft_id},
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

        return {
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
            "status": "sent",
        }
