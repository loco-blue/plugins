# openrouter

OpenRouter provider plugin for Loco — unified LLM, embedding, and rerank models
from 300+ upstream providers (Anthropic, OpenAI, Google, Meta, DeepSeek, Qwen, ...).

## Overview

**Type:** node (AI provider)
**Version:** 0.1.0
**Author:** loco

## Architecture

This plugin implements `OpenRouterProvider(AIProviderPlugin)` in `ai/provider.py`:

- **LLM** (`invoke` / `stream`) — via the `openai` SDK's `AsyncOpenAI` client,
  pointed at OpenRouter's OpenAI-compatible chat-completions endpoint
  (`https://openrouter.ai/api/v1`).
- **Embedding** (`embed`) — same `AsyncOpenAI` client, OpenRouter's OpenAI-compatible
  embeddings endpoint.
- **Rerank** (`rerank`) — OpenRouter's dedicated `/v1/rerank` endpoint, called
  directly via `httpx` since it is not OpenAI-compatible.

Model IDs use OpenRouter's `<upstream-provider>/<model-slug>` convention (see
`ai/openrouter.yaml` for the full catalog).

### Free Tier (Auto)

`openrouter/free` is listed as a normal `llm` model (label "Free Tier (Auto)").
It is a real OpenRouter model that OpenRouter itself auto-routes, server-side,
to whichever free model is currently available — the plugin sends it through
the same `invoke`/`stream` path as any other model, with no client-side
fallback or rotation logic of its own.

## Configuration

Configure credentials via `auth/openrouter.yaml`:

```yaml
credentials_schema:
  - name: api_key
    type: secret
    required: true
  - name: http_referer # optional — used by OpenRouter for app rankings
    type: string
    required: false
  - name: app_name # optional — sent as the X-Title header
    type: string
    required: false
```

## Development

### Testing

```bash
cd plugins/openrouter
pytest tests/ -v
```

Or via the Loco CLI from the `loco/` directory:

```bash
uv run loco plugin validate ../plugins/openrouter
uv run loco plugin test ../plugins/openrouter
```

### Building

```bash
uv run loco plugin build ../plugins/openrouter
```

## License

MIT
