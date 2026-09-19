"""OpenRouter provider plugin.

Provides unified access to LLM, embedding, and rerank models from 300+
upstream providers via OpenRouter's OpenAI-compatible API
(chat completions, embeddings) and its dedicated rerank endpoint.
"""

from typing import Any

import httpx
from openai import AsyncOpenAI

from loco_sdk import OpenAICompatiblePlugin
from loco_sdk.types import EmbedResult, RerankItem, RerankResult

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_RERANK_URL = "https://openrouter.ai/api/v1/rerank"


class OpenRouterProvider(OpenAICompatiblePlugin):
    """OpenRouter provider supporting LLM, embedding, and rerank models.

    `invoke`/`stream`/`validate_credentials`/`list_models`/`get_model_info`
    all come from `OpenAICompatiblePlugin` unchanged — OpenRouter's wire
    format is the plain OpenAI shape with no quirks. Only `_get_client`
    (its own headers/base URL), `embed`, and `rerank` (its own
    non-OpenAI-compatible endpoint) are provider-specific.

    Features:
    - OpenAI-compatible chat completions and embeddings across 300+
      upstream providers (Anthropic, OpenAI, Google, Meta, DeepSeek, ...)
    - Dedicated /v1/rerank endpoint for reranking
    - Function calling and streaming support
    - `openrouter/free` is a real OpenRouter model that auto-routes each
      request to whichever free model is currently available — no
      client-side fallback logic is needed for it, it behaves like any
      other model here.
    """

    provider_name = "openrouter"
    supported_model_types = ["llm", "embedding", "rerank"]
    supported_models = [
        "anthropic/claude-5-sonnet",
        "anthropic/claude-5-opus",
        "openai/gpt-5.4",
        "openai/gpt-5.4-mini",
        "google/gemini-3.7-pro",
        "google/gemini-3.7-flash",
        "deepseek/deepseek-v4-pro",
        "meta-llama/llama-4.2-70b-instruct",
        "x-ai/grok-4.3",
        "qwen/qwen3.7-max",
        "moonshotai/kimi-k3",
        "openrouter/free",
    ]
    default_context_window = 131072
    default_max_output_tokens = 8192

    def _get_client(self) -> AsyncOpenAI:
        """Create OpenRouter client instance (OpenAI-compatible).

        Returns:
            Configured AsyncOpenAI client pointed at OpenRouter.
        """
        api_key = self._credentials.get("api_key", "")
        base_url = self._credentials.get("base_url", OPENROUTER_BASE_URL)

        default_headers = {}
        if self._credentials.get("http_referer"):
            default_headers["HTTP-Referer"] = self._credentials["http_referer"]
        if self._credentials.get("app_name"):
            default_headers["X-Title"] = self._credentials["app_name"]

        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=default_headers or None,
            http_client=httpx.AsyncClient(verify=False),
        )

    async def embed(
        self,
        model: str,
        texts: list[str],
        *,
        dimensions: int | None = None,
        **kwargs: Any,
    ) -> EmbedResult:
        """Generate embeddings via OpenRouter's OpenAI-compatible endpoint."""
        client = self._get_client()

        params: dict[str, Any] = {"model": model, "input": texts}
        if dimensions is not None:
            params["dimensions"] = dimensions

        response = await client.embeddings.create(**params)
        embeddings = [item.embedding for item in response.data]
        return EmbedResult(embeddings=embeddings)

    async def rerank(
        self,
        model: str,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
        **kwargs: Any,
    ) -> RerankResult:
        """Rerank documents via OpenRouter's dedicated /v1/rerank endpoint.

        This endpoint is not OpenAI-compatible, so it's called directly
        via httpx instead of through the AsyncOpenAI client.
        """
        api_key = self._credentials.get("api_key", "")

        payload: dict[str, Any] = {
            "model": model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        async with httpx.AsyncClient(verify=False) as http_client:
            response = await http_client.post(
                OPENROUTER_RERANK_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        results = [
            RerankItem(index=item["index"], score=item["relevance_score"])
            for item in data.get("results", [])
        ]
        return RerankResult(results=results)
