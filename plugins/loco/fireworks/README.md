# fireworks

Fireworks AI provider plugin for Loco — serverless LLM, embedding, and rerank models.

## Overview

**Type:** node (AI provider)
**Version:** 0.1.1
**Author:** loco

## Architecture

This plugin implements `FireworksProvider(AIProviderPlugin)` in `ai/provider.py`:

- **LLM** (`invoke` / `stream`) — via the `openai` SDK's `AsyncOpenAI` client,
  pointed at Fireworks' OpenAI-compatible chat-completions endpoint
  (`https://api.fireworks.ai/inference/v1`).
- **Embedding** (`embed`) — same `AsyncOpenAI` client, Fireworks' OpenAI-compatible
  embeddings endpoint.
- **Rerank** (`rerank`) — Fireworks' dedicated `/v1/rerank` endpoint, called
  directly via `httpx` since it is not OpenAI-compatible.

Model IDs use Fireworks' `accounts/fireworks/models/<slug>` convention (see
`ai/fireworks.yaml` for the full catalog).

## Configuration

Configure credentials via `auth/fireworks.yaml`:

```yaml
credentials_schema:
  - name: api_key
    type: secret
    required: true
```

## Development

### Testing

```bash
cd plugins/fireworks
pytest tests/ -v
```

Or via the Loco CLI from the `loco/` directory:

```bash
uv run loco plugin validate ../plugins/fireworks
uv run loco plugin test ../plugins/fireworks
```

### Building

```bash
uv run loco plugin build ../plugins/fireworks
```

## License

MIT
