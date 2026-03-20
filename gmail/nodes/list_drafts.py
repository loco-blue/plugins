"""
List Drafts - Gmail API Node

List and search draft emails
"""

from typing import Any
import logging

import httpx
from loco_sdk import NodePlugin, AuthContext

logger = logging.getLogger(__name__)


class ListDraftsNode(NodePlugin):
    """List draft emails in Gmail"""

    async def execute(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        List draft emails in Gmail.

        Args:
            inputs: Input values:
                - query: Optional search query
                - max_results: Maximum number of results (default: 10)
                - include_body: Include draft body in results (default: false)
            context: Workflow execution context with auth credentials.

        Returns:
            Output values:
                - drafts: List of draft objects
                - total: Total number of drafts
        """
        # Get auth context and wrap with AuthContext helper
        auth_data = context.get("auth")
        if not auth_data:
            raise ValueError(
                "OAuth authentication required. Please authorize Gmail access."
            )

        auth = AuthContext(auth_data)

        query = inputs.get("query", "")
        max_results = min(inputs.get("max_results", 10), 100)
        include_body = inputs.get("include_body", False)

        logger.info("Listing Gmail drafts")

        headers = auth.get_header()

        async with httpx.AsyncClient() as client:
            # List drafts
            list_url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
            params = {"maxResults": max_results}
            if query:
                params["q"] = query

            response = await client.get(
                list_url,
                headers=headers,
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            drafts_list = data.get("drafts", [])

            # Fetch full details if requested
            detailed_drafts = []
            for draft in drafts_list:
                draft_id = draft["id"]
                if include_body:
                    draft_url = f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}"
                    draft_response = await client.get(
                        draft_url,
                        headers=headers,
                        params={"format": "full"},
                        timeout=30.0,
                    )
                    draft_response.raise_for_status()
                    draft_data = draft_response.json()
                    detailed_drafts.append(self._parse_draft(draft_data))
                else:
                    detailed_drafts.append(
                        {
                            "id": draft_id,
                            "message_id": draft.get("message", {}).get("id"),
                        }
                    )

        return {
            "drafts": detailed_drafts,
            "total": len(drafts_list),
        }

    def _parse_draft(self, draft: dict) -> dict:
        """Parse draft data into simplified format."""
        message = draft.get("message", {})
        payload = message.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

        return {
            "id": draft.get("id"),
            "message_id": message.get("id"),
            "subject": headers.get("Subject", ""),
            "to": headers.get("To", ""),
            "snippet": message.get("snippet", ""),
        }
