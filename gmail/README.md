# Gmail Plugin

Gmail API integration for Loco - Send emails, search messages, manage drafts, and more.

## Overview

**Type:** node  
**Version:** 0.1.0  
**Author:** loco  
**Provider:** Google OAuth 2.0

## Installation

1. Install the plugin through Loco's plugin management system
2. Configure OAuth credentials in Google Cloud Console
3. Set up OAuth client in Loco admin panel
4. Users authorize Gmail access via OAuth flow

## Features

### ✅ Implemented Nodes

#### 1. **search_messages** (⭐ Priority)

Search emails using Gmail query operators.

**Inputs:**

- `query` - Gmail search query (e.g., "from:user@example.com subject:important")
- `max_results` - Maximum results (1-100, default: 10)
- `include_spam_trash` - Include spam/trash folders (default: false)

**Outputs:**

- `messages` - Array of message objects with details
- `total_results` - Total matching messages

**Query Operators:**

- `from:user@example.com` - From specific sender
- `to:user@example.com` - To specific recipient
- `subject:keyword` - Subject contains keyword
- `after:2024/01/01` - After date
- `before:2024/12/31` - Before date
- `has:attachment` - Has attachments
- `is:unread` - Unread messages
- `is:starred` - Starred messages
- `label:Important` - Has label

#### 2. **send_message** (⭐ Priority)

Send email immediately via Gmail API.

**Inputs:**

- `to` - Recipient email(s) (comma-separated)
- `subject` - Email subject
- `body` - Email body text
- `cc` - CC recipients (optional)
- `bcc` - BCC recipients (optional)
- `reply_to` - Reply-to address (optional)

**Outputs:**

- `message_id` - Gmail message ID
- `thread_id` - Thread ID
- `status` - Send status

#### 3. **get_message**

Get detailed message information including attachments metadata.

**Inputs:**

- `message_id` - Gmail message ID

**Outputs:**

- `message` - Detailed message object with headers, body, attachments

#### 4. **list_drafts**

List and search draft emails.

**Inputs:**

- `query` - Optional search query
- `max_results` - Maximum results (default: 10)
- `include_body` - Include draft body (default: false)

**Outputs:**

- `drafts` - Array of draft objects
- `total` - Total number of drafts

#### 5. **send_draft**

Send an existing draft email.

**Inputs:**

- `draft_id` - Gmail draft ID (or message_id)

**Outputs:**

- `message_id` - Sent message ID
- `thread_id` - Thread ID
- `status` - Send status

**Note:** Automatically handles both draft_id and message_id inputs.

#### 6. **flag_message**

Star/unstar messages for follow-up.

**Inputs:**

- `message_id` - Gmail message ID
- `action` - 'star' or 'unstar'

**Outputs:**

- `message_id` - Message ID
- `labels` - Updated label IDs
- `status` - Operation status

### 📌 Planned Nodes (Requires File Handling)

#### 7. **draft_message** 🚧

Create draft email with optional attachments.

**Status:** Not implemented - requires file handling integration  
**Reason:** Need to resolve how Loco handles file inputs in plugin context

**Planned Inputs:**

- `to` - Recipient email(s)
- `subject` - Email subject
- `body` - Email body text
- `attachments` - File objects (TBD)

**Planned Outputs:**

- `draft_id` - Created draft ID
- `message_id` - Message ID

#### 8. **add_attachment_to_draft** 🚧

Add file attachments to existing draft.

**Status:** Not implemented - requires complex MIME handling + file system  
**Complexity:** High - needs email.parser, MIME multipart modification  
**Reason:** Need to understand Loco's file object structure and storage

**Planned Inputs:**

- `draft_id` - Draft ID to modify
- `files` - Array of file objects (TBD)

**Planned Outputs:**

- `draft_id` - Updated draft ID
- `attachment_count` - Number of attachments added

**Technical Requirements:**

- MIME multipart message parsing with `email.parser.BytesParser`
- Base64 encoding for attachments
- File object handling in Loco context
- Draft raw message fetch & update

**Reference Implementation:**
See Dify's `add_attachment_to_draft.py` for MIME manipulation patterns.

## Architecture

This plugin uses **OAuth 2.0** authentication with Google and the **NodePlugin** base class for execution.

### Authentication Pattern

```python
class GmailNode(NodePlugin):
    async def execute(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any]
    ) -> dict[str, Any]:
        # Get unified auth context
        auth = context["auth"]

        # Get Authorization header (no need to check OAuth vs API Key)
        headers = auth.get_header()  # {"Authorization": "Bearer <token>"}

        # Make Gmail API request
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers=headers
            )

        return {"result": response.json()}
```

**Key Features:**

- ✅ Unified AuthContext - same interface for OAuth/API Key
- ✅ Automatic token refresh with circuit breaker
- ✅ Lazy refresh (only when needed)
- ✅ Works in both standalone and distributed modes

### Gmail API Scopes

The plugin requires these Gmail API scopes:

- `https://www.googleapis.com/auth/gmail.readonly` - Read emails
- `https://www.googleapis.com/auth/gmail.send` - Send emails
- `https://www.googleapis.com/auth/gmail.compose` - Create drafts
- `https://www.googleapis.com/auth/gmail.modify` - Modify emails (star/unstar)
- `https://www.googleapis.com/auth/gmail.labels` - Manage labels

### Execution Flow

```
Workflow Engine → PluginNode (proxy) → SandboxService → GmailNode.execute()
```

The plugin code runs on the sandbox server in an isolated environment with its own dependencies.

## Usage

### OAuth Setup (Admin)

1. **Create Google OAuth Client:**
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create OAuth 2.0 credentials
   - Add authorized redirect URI: `https://your-domain.com/api/plugins/oauth/callback`

2. **Configure in Loco:**
   ```bash
   POST /api/plugins/gmail/oauth/client
   {
     "client_id": "your-google-client-id",
     "client_secret": "your-google-client-secret"
   }
   ```

### User Authorization

Users must authorize Gmail access before using the plugin:

```bash
# Get authorization URL
GET /api/plugins/gmail/oauth/authorize?provider=google

# User completes OAuth flow
# Callback: /api/plugins/oauth/callback?code=...&state=...

# Check authorization status
GET /api/plugins/gmail/oauth/status?provider=google
```

### Example Workflow

```yaml
nodes:
  - id: search_emails
    type: plugin
    plugin: gmail
    node: search_messages
    inputs:
      query: "from:boss@company.com is:unread"
      max_results: 50

  - id: send_reply
    type: plugin
    plugin: gmail
    node: send_message
    inputs:
      to: "{{search_emails.messages[0].from}}"
      subject: "Re: {{search_emails.messages[0].subject}}"
      body: "Thank you for your email!"
```

## Development

### Prerequisites

- Python 3.11+
- Loco platform installed
- Google Cloud Console project with Gmail API enabled

### Local Setup

```bash
cd loco/plugins/gmail

# Install dependencies
pip install httpx

# Validate plugin structure
loco plugin validate .

# Test nodes (requires OAuth setup)
loco plugin test .
```

### Testing Individual Nodes

```python
from nodes.search_messages import SearchMessagesNode
from loco.shared.plugin.auth_context import AuthContext, AuthType

# Mock auth context for testing
auth = AuthContext(
    auth_type=AuthType.OAUTH2,
    provider="google",
    access_token="your-test-token"
)

# Test node
node = SearchMessagesNode()
result = await node.execute(
    inputs={"query": "is:unread", "max_results": 10},
    context={"auth": auth}
)
print(result["messages"])
```

### Adding New Nodes

```bash
# Generate node template
loco plugin node add <node_name> --template api --plugin-path .

# Implement execute() method in nodes/<node_name>.py
# Update nodes/<node_name>.yaml with proper inputs/outputs
# Add OAuth usage: auth = context["auth"]; headers = auth.get_header()
```

### Contributing

When implementing file-related nodes (draft_message, add_attachment_to_draft):

1. **Check Loco file handling:**
   - How are files passed in `inputs`?
   - File object structure (path, buffer, stream?)
   - Temporary file storage location

2. **MIME Implementation:**
   - Use `email.parser.BytesParser` for parsing
   - Use `email.mime.multipart.MIMEMultipart` for building
   - Base64 encode with `base64.urlsafe_b64encode`

3. **Reference:**
   - See Dify's implementation: [dify-official-plugins/tools/gmail](https://github.com/langgenius/dify-official-plugins/tree/main/tools/gmail)
   - Focus on `add_attachment_to_draft.py` for MIME manipulation patterns

## Troubleshooting

### OAuth Issues

**Token expired errors:**

- Loco automatically refreshes tokens with circuit breaker
- Check OAuth client credentials are correct
- Verify callback URL is whitelisted in Google Console

**Insufficient permissions:**

- Ensure all 5 Gmail scopes are configured in `provider/google.yaml`
- User may need to re-authorize with new scopes

### API Errors

**404 Draft not found:**

- `send_draft` node handles both draft_id and message_id
- Use `list_drafts` to verify draft exists

**429 Rate limit:**

- Gmail API has quotas (10,000 requests/day)
- Implement exponential backoff in production

## Known Limitations

1. **File attachments not supported yet** - Nodes 7-8 pending file system integration
2. **No batch operations** - Each node processes one email at a time
3. **Limited to 100 results** - Gmail API pagination not fully implemented
4. **Text-only emails** - HTML email composition not in current nodes

## Roadmap

- [ ] Implement `draft_message` node (waiting for file handling design)
- [ ] Implement `add_attachment_to_draft` node (complex MIME)
- [ ] Add batch send operations
- [ ] Support HTML email templates
- [ ] Implement pagination for search results
- [ ] Add email thread management nodes
- [ ] Support Gmail filters and rules

## License

MIT

## Resources

- **Loco Documentation:** https://docs.loco.dev/plugins
- **Gmail API Reference:** https://developers.google.com/gmail/api
- **OAuth 2.0 Guide:** https://developers.google.com/identity/protocols/oauth2
- **Reference Implementation:** [Dify Gmail Plugin](https://github.com/langgenius/dify-official-plugins/tree/main/tools/gmail)

## Support

- **Issues:** https://github.com/your-org/loco/issues
- **Discord:** Join #plugins channel
- **Email:** support@loco.dev
