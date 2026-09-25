"""
Search Messages - Gmail API Node

Search emails using Gmail query operators
"""

from typing import Any
import logging
import base64
import html

import httpx
from loco_sdk import NodePlugin, AuthContext

logger = logging.getLogger(__name__)


class SearchMessagesNode(NodePlugin):
    """Search emails using Gmail API with advanced query operators"""

    async def execute(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Search emails in Gmail using query operators.

        Args:
            inputs: Input values:
                - query: Gmail search query (e.g., "from:user@example.com subject:important")
                - max_results: Maximum number of results (default: 10)
                - include_spam_trash: Include spam and trash (default: false)
            context: Workflow execution context with auth credentials.

        Returns:
            Output values:
                - messages: List of message objects with details
                - total_results: Total number of matching messages
        """
        # Get auth context and wrap with AuthContext helper
        auth_data = context.get("auth")
        if not auth_data:
            raise ValueError(
                "OAuth authentication required. Please authorize Gmail access."
            )

        auth = AuthContext(auth_data)

        query = inputs.get("query", "")
        max_results = min(inputs.get("max_results", 10), 100)  # Cap at 100
        include_spam_trash = inputs.get("include_spam_trash", False)

        logger.info(f"Searching Gmail with query: {query}")

        # Get Authorization header
        headers = auth.get_header()

        async with httpx.AsyncClient() as client:
            # Search for message IDs
            search_url = (
                "https://gmail.googleapis.com/gmail/v1/users/me/messages"
            )
            search_params = {
                "q": query,
                "maxResults": max_results,
                "includeSpamTrash": str(include_spam_trash).lower(),
            }

            try:
                search_response = await client.get(
                    search_url,
                    headers=headers,
                    params=search_params,
                    timeout=30.0,
                )
                search_response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    error_detail = (
                        e.response.json() if e.response.content else {}
                    )
                    error_msg = error_detail.get("error", {}).get(
                        "message", "Unknown error"
                    )
                    raise ValueError(
                        f"Gmail API access denied (403 Forbidden): {error_msg}. "
                        "Possible causes:\n"
                        "1. Access token has been revoked - please re-authorize\n"
                        "2. Gmail API is not enabled in your Google Cloud project\n"
                        "3. Missing required OAuth scopes\n"
                        "4. Token expired but cannot refresh (no refresh token available)"
                    ) from e
                elif e.response.status_code == 401:
                    raise ValueError(
                        "Gmail API authentication failed (401 Unauthorized). "
                        "Your access token is invalid or expired. Please re-authorize Gmail access."
                    ) from e
                else:
                    raise

            search_data = search_response.json()

            messages_list = search_data.get("messages", [])
            result_size = search_data.get("resultSizeEstimate", 0)

            # Fetch full details for each message
            detailed_messages = []
            for msg in messages_list:
                msg_id = msg["id"]
                msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}"

                msg_response = await client.get(
                    msg_url,
                    headers=headers,
                    params={"format": "full"},
                    timeout=30.0,
                )
                msg_response.raise_for_status()
                msg_data = msg_response.json()

                # Parse message
                parsed = self._parse_message(msg_data)
                detailed_messages.append(parsed)

        return {
            "messages": detailed_messages,
            "total_results": result_size,
        }

    def _parse_message(self, message: dict) -> dict:
        """Parse Gmail message data into simplified format."""
        headers = {
            h["name"]: h["value"]
            for h in message.get("payload", {}).get("headers", [])
        }

        return {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "snippet": message.get("snippet", ""),
            "labels": message.get("labelIds", []),
            "body": self._extract_body(message.get("payload", {})),
            "attachments": self._count_attachments(message.get("payload", {})),
        }

    def _extract_body(self, payload: dict) -> str:
        """Extract email body from payload."""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    body_data = part.get("body", {}).get("data", "")
                    return self._decode_base64(body_data)
                elif part.get("mimeType") == "text/html":
                    body_data = part.get("body", {}).get("data", "")
                    html_body = self._decode_base64(body_data)
                    return self._html_to_text(html_body)
        else:
            body_data = payload.get("body", {}).get("data", "")
            return self._decode_base64(body_data)
        return ""

    def _decode_base64(self, data: str) -> str:
        """Decode base64url encoded string."""
        if not data:
            return ""
        try:
            decoded_bytes = base64.urlsafe_b64decode(
                data + "=" * (4 - len(data) % 4)
            )
            return decoded_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _html_to_text(self, html_text: str) -> str:
        """Convert HTML to plain text."""
        text = html.unescape(html_text)
        # Basic HTML tag removal
        import re

        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _count_attachments(self, payload: dict) -> int:
        """Count number of attachments in message."""
        count = 0
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("filename"):
                    count += 1
        return count
