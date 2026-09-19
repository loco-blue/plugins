"""Fireworks AI provider plugin.

Provides access to Fireworks AI's serverless LLM, embedding, and rerank
models via an OpenAI-compatible API (LLM/embedding) and a dedicated
rerank endpoint.
"""

from typing import Any

import httpx
from openai import AsyncOpenAI

from loco_sdk import OpenAICompatiblePlugin
from loco_sdk.types import EmbedResult, RerankItem, RerankResult

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
FIREWORKS_RERANK_URL = "https://api.fireworks.ai/inference/v1/rerank"


class FireworksProvider(OpenAICompatiblePlugin):
    """Fireworks AI provider supporting LLM, embedding, and rerank models.

    `invoke`/`stream`/`validate_credentials`/`list_models`/`get_model_info`
    all come from `OpenAICompatiblePlugin` unchanged — Fireworks' wire
    format is the plain OpenAI shape with no quirks. Only `_get_client`,
    `embed`, and `rerank` (its own non-OpenAI-compatible endpoint) are
    provider-specific.

    Features:
    - OpenAI-compatible chat completions and embeddings
    - Dedicated /v1/rerank endpoint for reranking
    - Function calling and streaming support
    """

    provider_name = "fireworks"
    supported_model_types = ["llm", "embedding", "rerank"]
    supported_models = [
        "accounts/fireworks/models/deepseek-v4-flash",
        "accounts/fireworks/models/deepseek-v4-pro",
        "accounts/fireworks/models/kimi-k2p6",
        "accounts/fireworks/models/kimi-k3",
        "accounts/fireworks/models/gpt-oss-20b",
        "accounts/fireworks/models/gpt-oss-120b",
        "accounts/fireworks/models/qwen3p7-plus",
        "accounts/fireworks/models/glm-5p2",
        "accounts/fireworks/models/minimax-m3",
    ]
    default_context_window = 131072
    default_max_output_tokens = 8192

    def _get_client(self) -> AsyncOpenAI:
        """Create Fireworks client instance (OpenAI-compatible).

        Returns:
            Configured AsyncOpenAI client pointed at Fireworks.
        """
        api_key = self._credentials.get("api_key", "")
        base_url = self._credentials.get("base_url", FIREWORKS_BASE_URL)

        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
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
        """Generate embeddings via Fireworks' OpenAI-compatible endpoint."""
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
        """Rerank documents via Fireworks' dedicated /v1/rerank endpoint.

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
                FIREWORKS_RERANK_URL,
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
