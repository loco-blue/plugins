"""
Draft Message - Gmail API Node

Create draft email (text only, no attachments)
Attachments are added separately via add_attachment_to_draft node
"""

from typing import Any
import logging
import base64
from email.message import EmailMessage

import httpx
from loco_sdk import NodePlugin, AuthContext

logger = logging.getLogger(__name__)


class DraftMessageNode(NodePlugin):
    """Create draft email via Gmail API."""

    async def execute(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create draft email.

        Args:
            inputs: Input values:
                - to: Recipient email(s) (comma-separated, required)
                - subject: Email subject (optional, default: "")
                - body: Email body text (optional, default: "")
                - cc: CC recipients (optional, comma-separated)
                - bcc: BCC recipients (optional, comma-separated)
                - reply_to: Reply-to email (optional)
            context: Workflow execution context with auth credentials.

        Returns:
            Output values:
                - draft_id: Gmail draft ID (e.g., "r-1234567890")
                - message_id: Gmail message ID (e.g., "18abc123def456")
                - status: "draft_created"

        Raises:
            ValueError: Missing/invalid inputs or auth
            httpx.HTTPStatusError: Gmail API errors

        Example:
            # In workflow:
            inputs = {
                "to": "recipient@example.com",
                "subject": "Meeting Tomorrow",
                "body": "Let's meet at 2pm.",
                "cc": "manager@example.com"
            }

            outputs = await node.execute(inputs, context)
            # outputs = {
            #     "draft_id": "r-1234567890",
            #     "message_id": "18abc123def456",
            #     "status": "draft_created"
            # }
        """
        # ========================================
        # 1. Validate Authentication
        # ========================================
        auth_data = context.get("auth")
        if not auth_data:
            raise ValueError(
                "OAuth authentication required. Please authorize Gmail access."
            )
        auth = AuthContext(auth_data)

        # ========================================
        # 2. Extract & Validate Inputs
        # ========================================
        to = inputs.get("to", "").strip()
        if not to:
            raise ValueError("Missing required input: to (recipient email)")

        # Validate email format
        if not self._validate_email_addresses(to):
            raise ValueError(f"Invalid email format in 'to': {to}")

        subject = inputs.get("subject", "").strip()
        body = inputs.get("body", "").strip()

        cc = inputs.get("cc", "").strip()
        if cc and not self._validate_email_addresses(cc):
            raise ValueError(f"Invalid email format in 'cc': {cc}")

        bcc = inputs.get("bcc", "").strip()
        if bcc and not self._validate_email_addresses(bcc):
            raise ValueError(f"Invalid email format in 'bcc': {bcc}")

        reply_to = inputs.get("reply_to", "").strip()
        if reply_to and not self._validate_email_addresses(reply_to):
            raise ValueError(f"Invalid email format in 'reply_to': {reply_to}")

        logger.info(f"Creating draft for recipient: {to}")

        # ========================================
        # 3. Build MIME Message
        # ========================================
        message_str = self._build_mime_message(
            to=to, subject=subject, body=body, cc=cc, bcc=bcc, reply_to=reply_to
        )

        # ========================================
        # 4. Encode to Base64
        # ========================================
        # Gmail API requires base64url encoding (RFC 4648)
        raw_message = base64.urlsafe_b64encode(
            message_str.encode("utf-8")
        ).decode("utf-8")

        # ========================================
        # 5. Create Draft via Gmail API
        # ========================================
        headers = auth.get_header()
        headers["Content-Type"] = "application/json"

        api_url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
        request_body = {"message": {"raw": raw_message}}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    api_url,
                    headers=headers,
                    json=request_body,
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise ValueError(
                        "Gmail API authentication failed. "
                        "Access token expired. Please re-authorize."
                    ) from e
                elif e.response.status_code == 403:
                    raise ValueError(
                        "Gmail API access denied. "
                        "Check OAuth scopes: gmail.compose is required."
                    ) from e
                else:
                    error_detail = (
                        e.response.json() if e.response.content else {}
                    )
                    error_msg = error_detail.get("error", {}).get(
                        "message", str(e)
                    )
                    raise ValueError(f"Gmail API error: {error_msg}") from e

        # ========================================
        # 6. Return Draft Reference
        # ========================================
        logger.info(f"Draft created successfully: {result.get('id')}")

        return {
            "draft_id": result.get("id"),  # e.g., "r-1234567890"
            "message_id": result.get("message", {}).get(
                "id"
            ),  # e.g., "18abc..."
            "status": "draft_created",
        }

    # ========================================
    # Helper Methods
    # ========================================

    def _build_mime_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        reply_to: str | None = None,
    ) -> str:
        """
        Build RFC 2822 compliant email message.

        Returns MIME text/plain message as string.
        This is intentionally simple - only text, no attachments.
        Attachments will be added later by add_attachment_to_draft.

        Args:
            to: Recipient(s), comma-separated
            subject: Email subject
            body: Email body (plain text)
            cc: CC recipient(s), comma-separated
            bcc: BCC recipient(s), comma-separated
            reply_to: Reply-to address

        Returns:
            MIME message as string

        Example:
            >>> msg = self._build_mime_message(
            ...     to="user@example.com",
            ...     subject="Hello",
            ...     body="Test message"
            ... )
            >>> print(msg)
            To: user@example.com
            Subject: Hello
            Content-Type: text/plain; charset="utf-8"
            ...
        """
        # Create EmailMessage (modern API, Python 3.6+)
        # Automatically handles charset and encoding properly
        message = EmailMessage()

        # Set headers
        message["To"] = to
        message["Subject"] = subject

        if cc:
            message["Cc"] = cc

        if bcc:
            message["Bcc"] = bcc

        if reply_to:
            message["Reply-To"] = reply_to

        # Set body content
        # EmailMessage handles encoding correctly without manual intervention
        message.set_content(body)

        # Convert to string
        # This produces RFC 2822 format that Gmail expects
        return message.as_string()

    def _validate_email_addresses(self, email_string: str) -> bool:
        """
        Basic email address validation.

        Validates format of single or comma-separated email addresses.
        Uses simple regex check (not RFC 5322 compliant, but practical).

        Args:
            email_string: Single email or comma-separated list

        Returns:
            True if all emails are valid format

        Example:
            >>> self._validate_email_addresses("user@example.com")
            True
            >>> self._validate_email_addresses("user@example.com, admin@test.org")
            True
            >>> self._validate_email_addresses("invalid-email")
            False
        """
        if not email_string:
            return True  # Empty is valid (optional field)

        # Split by comma and strip whitespace
        addresses = [addr.strip() for addr in email_string.split(",")]

        # Basic validation: must have @ and . after @
        for address in addresses:
            if not address:
                continue

            # Must contain @ symbol
            if "@" not in address:
                return False

            # Must have domain with dot
            local, domain = address.rsplit("@", 1)
            if not local or not domain or "." not in domain:
                return False

        return True
