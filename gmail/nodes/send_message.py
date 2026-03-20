"""
Send Message - Gmail API Node

Send email via Gmail API
"""

from typing import Any
import logging
import base64
from email.mime.text import MIMEText

import httpx
from loco_sdk import NodePlugin, AuthContext

logger = logging.getLogger(__name__)


class SendMessageNode(NodePlugin):
    """Send email via Gmail API"""

    async def execute(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Send email via Gmail API.

        Args:
            inputs: Input values:
                - to: Recipient email(s) (comma-separated)
                - subject: Email subject
                - body: Email body text
                - cc: CC recipients (optional, comma-separated)
                - bcc: BCC recipients (optional, comma-separated)
                - reply_to: Reply-to email (optional)
            context: Workflow execution context with auth credentials.

        Returns:
            Output values:
                - message_id: Gmail message ID
                - thread_id: Thread ID
                - status: Success status
        """
        # Get auth context and wrap with AuthContext helper
        auth_data = context.get("auth")
        if not auth_data:
            raise ValueError(
                "OAuth authentication required. Please authorize Gmail access."
            )

        auth = AuthContext(auth_data)

        to = inputs.get("to")
        if not to:
            raise ValueError("Missing required input: to")

        subject = inputs.get("subject", "")
        body = inputs.get("body", "")
        cc = inputs.get("cc")
        bcc = inputs.get("bcc")
        reply_to = inputs.get("reply_to")

        logger.info(f"Sending email to {to}")

        # Build MIME message
        message = self._build_message(to, subject, body, cc, bcc, reply_to)

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.encode()).decode()

        # Get Authorization header
        headers = auth.get_header()
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers=headers,
                json={"raw": raw_message},
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

        return {
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
            "status": "sent",
        }

    def _build_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        reply_to: str | None = None,
    ) -> str:
        """Build RFC 2822 formatted email message."""
        msg = MIMEText(body)
        msg["To"] = to
        msg["Subject"] = subject

        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc
        if reply_to:
            msg["Reply-To"] = reply_to

        return msg.as_string()
