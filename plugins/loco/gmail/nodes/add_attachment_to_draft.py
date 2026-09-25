"""
Add Attachment To Draft - Gmail API Node

Add file attachments to existing draft email
Uses PluginFile format (base64-encoded, sandbox-compatible)
"""

from typing import Any
import logging
import base64
from email import message_from_bytes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import httpx
from loco_sdk import NodePlugin, AuthContext
from loco_sdk.plugin import PluginFile, is_plugin_file

logger = logging.getLogger(__name__)

# Gmail attachment size limit
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25MB


class AddAttachmentToDraftNode(NodePlugin):
    """Add attachments to Gmail draft."""

    async def execute(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Add attachments to an existing Gmail draft.

        This node works with PluginFile format - the PluginNode wrapper
        automatically converts FileRef → PluginFile before calling this method.

        Process:
        1. Fetch draft as RAW MIME from Gmail
        2. Parse MIME message
        3. Convert to multipart if needed
        4. Add attachments from PluginFile(s)
        5. Update draft with new MIME

        Args:
            inputs: Input values:
                - draft_id: Gmail draft ID (required)
                - file_to_attach: PluginFile or array of PluginFiles (required)
                    Format: {
                        "_type": "_plugin_file",
                        "filename": "report.pdf",
                        "content_base64": "...",
                        "mimetype": "application/pdf",
                        "size": 102400
                    }
            context: Workflow execution context with auth credentials.

        Returns:
            Output values:
                - draft_id: Updated draft ID
                - message_id: Updated message ID
                - attachments_added: Number of attachments added
                - total_size: Total size of attachments in bytes
                - status: "attachments_added"

        Raises:
            ValueError: Invalid inputs or file too large
            httpx.HTTPStatusError: Gmail API errors

        Example workflow:
            Node 1 (draft_message):
                outputs = {"draft_id": "r-123", ...}

            Node 2 (add_attachment_to_draft):
                inputs = {
                    "draft_id": "{{draft_message.draft_id}}",
                    "file_to_attach": "{{start.document}}"  # FileRef
                }
                # PluginNode wrapper converts FileRef → PluginFile automatically
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
        draft_id = inputs.get("draft_id", "").strip()
        if not draft_id:
            raise ValueError("Missing required input: draft_id")

        files_to_attach = inputs.get("file_to_attach")
        if not files_to_attach:
            raise ValueError("Missing required input: file_to_attach")

        # Support single file or array of files
        if not isinstance(files_to_attach, list):
            files_to_attach = [files_to_attach]

        # ========================================
        # 3. Convert to PluginFile objects
        # ========================================
        plugin_files = []
        for file_data in files_to_attach:
            if not is_plugin_file(file_data):
                raise ValueError(
                    "file_to_attach must be file(s). "
                    f"Got: {type(file_data).__name__}"
                )

            # PluginFile.from_dict automatically decodes base64
            try:
                plugin_file = PluginFile.from_dict(file_data)
                plugin_files.append(plugin_file)
            except Exception as e:
                raise ValueError(f"Failed to parse file: {e}") from e

        # ========================================
        # 4. Validate file sizes (Gmail limit: 25MB)
        # ========================================
        for plugin_file in plugin_files:
            if plugin_file.size > MAX_ATTACHMENT_SIZE:
                raise ValueError(
                    f"File too large: {plugin_file.filename} "
                    f"({plugin_file.size:,} bytes). "
                    f"Gmail limit is {MAX_ATTACHMENT_SIZE:,} bytes (25MB)."
                )

        total_size = sum(f.size for f in plugin_files)
        logger.info(
            f"Adding {len(plugin_files)} attachment(s) to draft {draft_id} "
            f"(total size: {total_size:,} bytes)"
        )

        # ========================================
        # 5. Fetch draft as RAW MIME
        # ========================================
        draft_mime = await self._fetch_draft_raw(draft_id, auth)

        # ========================================
        # 6. Parse MIME and add attachments
        # ========================================
        # Decode draft MIME from base64
        mime_bytes = base64.urlsafe_b64decode(draft_mime + "===")
        original_msg = message_from_bytes(mime_bytes)

        # Convert to multipart if needed
        if not original_msg.is_multipart():
            logger.debug("Converting text/plain draft to multipart")
            multipart = MIMEMultipart()

            # Copy headers
            for key, value in original_msg.items():
                multipart[key] = value

            # Add original body as first part
            body_text = original_msg.get_payload()
            multipart.attach(MIMEText(body_text, "plain", "utf-8"))

            msg = multipart
        else:
            msg = original_msg

        # Add each attachment
        for plugin_file in plugin_files:
            logger.debug(
                f"Attaching file: {plugin_file.filename} "
                f"({plugin_file.size:,} bytes, {plugin_file.mimetype})"
            )

            # Create MIME attachment part
            main_type, sub_type = plugin_file.mimetype.split("/", 1)
            part = MIMEBase(main_type, sub_type)
            part.set_payload(plugin_file.content)  # ← Binary from PluginFile
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{plugin_file.filename}"',
            )
            msg.attach(part)

        # ========================================
        # 7. Update draft with new MIME
        # ========================================
        new_raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        updated_draft = await self._update_draft(draft_id, new_raw, auth)

        # ========================================
        # 8. Return result
        # ========================================
        logger.info(
            f"Successfully added {len(plugin_files)} attachment(s) to draft {draft_id}"
        )

        return {
            "draft_id": updated_draft["id"],
            "message_id": updated_draft["message"]["id"],
            "attachments_added": len(plugin_files),
            "total_size": total_size,
            "filenames": [f.filename for f in plugin_files],
            "status": "attachments_added",
        }

    # ========================================
    # Helper Methods
    # ========================================

    async def _fetch_draft_raw(self, draft_id: str, auth: AuthContext) -> str:
        """
        Fetch draft as RAW MIME from Gmail API.

        Args:
            draft_id: Gmail draft ID
            auth: Authentication context

        Returns:
            Base64-encoded MIME message

        Raises:
            httpx.HTTPStatusError: If draft not found or API error
        """
        async with httpx.AsyncClient() as client:
            url = (
                f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}"
                "?format=raw"
            )

            try:
                response = await client.get(
                    url, headers=auth.get_header(), timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                return data["message"]["raw"]

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise ValueError(
                        f"Draft not found: {draft_id}. "
                        "It may have been deleted or sent."
                    ) from e
                elif e.response.status_code == 401:
                    raise ValueError(
                        "Gmail API authentication failed. "
                        "Access token expired. Please re-authorize."
                    ) from e
                else:
                    raise

    async def _update_draft(
        self, draft_id: str, raw_mime: str, auth: AuthContext
    ) -> dict:
        """
        Update draft with new MIME via Gmail API.

        Args:
            draft_id: Gmail draft ID
            raw_mime: Base64-encoded MIME message
            auth: Authentication context

        Returns:
            Updated draft data from Gmail API

        Raises:
            httpx.HTTPStatusError: If update fails
        """
        async with httpx.AsyncClient() as client:
            url = f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}"

            headers = auth.get_header()
            headers["Content-Type"] = "application/json"

            request_body = {"id": draft_id, "message": {"raw": raw_mime}}

            try:
                response = await client.put(
                    url,
                    headers=headers,
                    json=request_body,
                    timeout=60.0,  # Longer timeout for large attachments
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 413:
                    raise ValueError(
                        "Attachment too large. Gmail API rejected the request. "
                        "Total email size (including all attachments) must be < 25MB."
                    ) from e
                elif e.response.status_code == 401:
                    raise ValueError(
                        "Gmail API authentication failed. "
                        "Access token expired. Please re-authorize."
                    ) from e
                else:
                    error_detail = (
                        e.response.json() if e.response.content else {}
                    )
                    error_msg = error_detail.get("error", {}).get(
                        "message", str(e)
                    )
                    raise ValueError(
                        f"Failed to update draft: {error_msg}"
                    ) from e
