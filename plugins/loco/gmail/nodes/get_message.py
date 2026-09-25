"""
Get Message - Gmail API Node

Get detailed message information including attachments
"""

from typing import Any
import logging
import base64

import httpx
from loco_sdk import NodePlugin, AuthContext

logger = logging.getLogger(__name__)


class GetMessageNode(NodePlugin):
    """Get detailed Gmail message information"""

    async def execute(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Get detailed information about a Gmail message.

        Args:
            inputs: Input values:
                - message_id: Gmail message ID
            context: Workflow execution context with auth credentials.

        Returns:
            Output values:
                - message: Detailed message object with headers, body, attachments
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

        logger.info(f"Fetching message: {message_id}")

        # Get Authorization header
        headers = auth.get_header()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
                headers=headers,
                params={"format": "full"},
                timeout=30.0,
            )
            response.raise_for_status()
            msg_data = response.json()

        # Parse message
        parsed_message = self._parse_message(msg_data)

        return {
            "message": parsed_message,
        }

    def _parse_message(self, message: dict) -> dict:
        """Parse Gmail message data into detailed format."""
        payload = message.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

        return {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "label_ids": message.get("labelIds", []),
            "snippet": message.get("snippet", ""),
            "size_estimate": message.get("sizeEstimate", 0),
            "internal_date": message.get("internalDate"),
            "headers": {
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "cc": headers.get("Cc", ""),
                "date": headers.get("Date", ""),
                "message_id": headers.get("Message-ID", ""),
            },
            "body": self._extract_body(payload),
            "attachments": self._extract_attachments(payload),
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
                    return self._decode_base64(body_data)
        else:
            body_data = payload.get("body", {}).get("data", "")
            return self._decode_base64(body_data)
        return ""

    def _extract_attachments(self, payload: dict) -> list[dict]:
        """Extract attachment metadata from payload."""
        attachments = []
        if "parts" in payload:
            for part in payload["parts"]:
                filename = part.get("filename")
                if filename:
                    attachments.append(
                        {
                            "filename": filename,
                            "mime_type": part.get("mimeType", ""),
                            "size": part.get("body", {}).get("size", 0),
                            "attachment_id": part.get("body", {}).get(
                                "attachmentId"
                            ),
                        }
                    )
        return attachments

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
