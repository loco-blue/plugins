"""Fireworks AI provider plugin.

Provides access to Fireworks AI's serverless LLM, embedding, and rerank
models via an OpenAI-compatible API (LLM/embedding) and a dedicated
rerank endpoint.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from loco_sdk import AIProviderPlugin
from loco_sdk.types import (
    Delta,
    EmbedResult,
    FunctionCall,
    LLMResult,
    Message,
    RerankItem,
    RerankResult,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
)

logger = logging.getLogger(__name__)

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
FIREWORKS_RERANK_URL = "https://api.fireworks.ai/inference/v1/rerank"


class FireworksProvider(AIProviderPlugin):
    """Fireworks AI provider supporting LLM, embedding, and rerank models.

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

    async def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        """Validate credentials by listing models.

        Args:
            credentials: Must contain "api_key"

        Returns:
            True if credentials are valid
        """
        api_key = credentials.get("api_key")
        if not api_key:
            return False

        try:
            old_credentials = self._credentials
            self._credentials = credentials

            client = self._get_client()
            await client.models.list()

            self._credentials = old_credentials
            return True
        except Exception as e:
            logger.warning(f"Failed to validate Fireworks credentials: {e}")
            self._credentials = old_credentials
            return False

    def _normalize_messages(
        self, messages: list[Message]
    ) -> list[dict[str, Any]]:
        """Serialize messages to Fireworks-compatible dicts."""
        return [msg.model_dump(exclude_none=True) for msg in messages]

    async def invoke(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> LLMResult:
        """Invoke LLM completion via Fireworks API."""
        client = self._get_client()

        raw_messages = self._normalize_messages(messages)
        raw_tools = (
            [t.model_dump(exclude_none=True) for t in tools] if tools else None
        )

        params: dict[str, Any] = {
            "model": model,
            "messages": raw_messages,
            "temperature": temperature,
        }

        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        if raw_tools:
            params["tools"] = raw_tools
            params["tool_choice"] = kwargs.get("tool_choice", "auto")

        for key in (
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
            "response_format",
        ):
            if key in kwargs:
                params[key] = kwargs[key]

        completion: ChatCompletion = await client.chat.completions.create(
            **params
        )

        choice = completion.choices[0]
        message = choice.message

        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    type=tc.type,
                    function=FunctionCall(
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    ),
                )
                for tc in message.tool_calls
            ]

        return LLMResult(
            content=message.content or "",
            tool_calls=tool_calls,
            usage=Usage(
                prompt_tokens=(
                    completion.usage.prompt_tokens if completion.usage else 0
                ),
                completion_tokens=(
                    completion.usage.completion_tokens
                    if completion.usage
                    else 0
                ),
                total_tokens=(
                    completion.usage.total_tokens if completion.usage else 0
                ),
            ),
            finish_reason=choice.finish_reason or "stop",
            model=completion.model,
        )

    async def stream(
        self,
        model: str,
        messages: list[Message],
        **kwargs: Any,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream LLM completion via Fireworks API."""
        client = self._get_client()

        raw_messages = self._normalize_messages(messages)

        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens")
        tools = kwargs.get("tools")
        raw_tools = (
            [t.model_dump(exclude_none=True) for t in tools] if tools else None
        )

        params: dict[str, Any] = {
            "model": model,
            "messages": raw_messages,
            "temperature": temperature,
            "stream": True,
            # Without this, the OpenAI-compatible streaming API (which
            # Fireworks implements) never includes a `usage` field on any
            # chunk — `chunk.usage` below would always be None, so every
            # message from this provider would persist with no token
            # usage regardless of how the response is parsed.
            "stream_options": {"include_usage": True},
        }

        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        if raw_tools:
            params["tools"] = raw_tools
            params["tool_choice"] = kwargs.get("tool_choice", "auto")

        for key in ("top_p", "frequency_penalty", "presence_penalty", "stop"):
            if key in kwargs:
                params[key] = kwargs[key]

        fireworks_stream = await client.chat.completions.create(**params)

        async for chunk in fireworks_stream:
            if not chunk.choices:
                # With `stream_options.include_usage=True`, usage arrives
                # on its own trailing chunk with an empty `choices` list —
                # not attached to the last content-bearing chunk. Yield it
                # as a usage-only StreamChunk instead of dropping it.
                if chunk.usage:
                    yield StreamChunk(
                        delta=Delta(),
                        usage=Usage(
                            prompt_tokens=chunk.usage.prompt_tokens,
                            completion_tokens=chunk.usage.completion_tokens,
                            total_tokens=chunk.usage.total_tokens,
                        ),
                        finish_reason=None,
                    )
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            content = delta.content if delta.content else None

            tool_calls = None
            if delta.tool_calls:
                tool_calls = [
                    ToolCall(
                        id=tc.id or "",
                        type=tc.type or "function",
                        function=FunctionCall(
                            name=(
                                tc.function.name
                                if tc.function and tc.function.name
                                else ""
                            ),
                            arguments=(
                                tc.function.arguments
                                if tc.function and tc.function.arguments
                                else ""
                            ),
                        ),
                        # Disambiguates which tool call these arguments
                        # belong to — without it, every chunk collapses
                        # onto the first tool call when several stream in
                        # the same turn (loco's consumer merges by index).
                        index=tc.index,
                    )
                    for tc in delta.tool_calls
                ]

            usage = None
            if chunk.usage:
                usage = Usage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                )

            yield StreamChunk(
                delta=Delta(content=content, tool_calls=tool_calls),
                usage=usage,
                finish_reason=choice.finish_reason,
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

    async def list_models(self) -> list[str]:
        """List available models from Fireworks API.

        Returns:
            List of model identifiers

        Note:
            This provides runtime model discovery in addition to
            the static models defined in ai.yaml.
        """
        try:
            client = self._get_client()
            models_page = await client.models.list()
            return [model.id for model in models_page.data]
        except Exception as e:
            logger.warning(f"Failed to list Fireworks models: {e}")
            return self.supported_models

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Return metadata for a single model.

        Args:
            model: Model identifier

        Returns:
            Model metadata dict
        """
        return {
            "model": model,
            "provider": self.provider_name,
            "context_window": 131072,  # Conservative default
            "max_output_tokens": 8192,
        }
