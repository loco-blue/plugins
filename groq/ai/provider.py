"""Groq AI provider plugin.

Provides fast AI inference via Groq LPU™ technology.
Uses official Groq Python client.
"""

import logging
from typing import Any
from collections.abc import AsyncGenerator

from groq import AsyncGroq
from groq.types.chat import ChatCompletion, ChatCompletionChunk

from loco_sdk import AIProviderPlugin
from loco_sdk.types import (
    Delta,
    FunctionCall,
    LLMResult,
    Message,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
)

logger = logging.getLogger(__name__)


class GroqProvider(AIProviderPlugin):
    """Groq AI provider supporting fast LLM inference.

    Features:
    - Ultra-fast inference with Groq LPU™
    - Official Groq Python client
    - Function calling support
    - JSON mode support
    """

    provider_name = "groq"
    supported_model_types = ["llm"]
    supported_models = [
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ]

    def _get_client(self) -> AsyncGroq:
        """Create Groq client instance.

        Returns:
            Configured AsyncGroq client
        """
        api_key = self._credentials.get("api_key", "")
        base_url = self._credentials.get("base_url")

        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url

        return AsyncGroq(**kwargs)

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
            # Temporarily set credentials to test
            old_credentials = self._credentials
            self._credentials = credentials

            client = self._get_client()
            await client.models.list()

            # Restore original credentials
            self._credentials = old_credentials
            return True
        except Exception as e:
            logger.warning(f"Failed to validate Groq credentials: {e}")
            self._credentials = old_credentials
            return False

    def _normalize_messages(
        self, messages: list[Message]
    ) -> list[dict[str, Any]]:
        """Serialize messages to Groq-compatible dicts.

        Groq requires image_url to be an object {"url": "..."}, not a string.
        Wraps any image_url string values before dumping.
        """
        result: list[dict[str, Any]] = []
        for msg in messages:
            dumped = msg.model_dump(exclude_none=True)
            content = dumped.get("content")
            if isinstance(content, list):
                normalized: list[dict[str, Any]] = []
                for part in content:
                    if part.get("type") == "image_url":
                        image_url = part.get("image_url")
                        if isinstance(image_url, str):
                            normalized.append(
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_url},
                                }
                            )
                        else:
                            normalized.append(part)
                    else:
                        normalized.append(part)
                dumped["content"] = normalized
            result.append(dumped)
        return result

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
        """Invoke LLM completion via Groq API."""
        client = self._get_client()

        # Serialize typed objects to dicts for Groq client
        raw_messages = self._normalize_messages(messages)
        raw_tools = (
            [t.model_dump(exclude_none=True) for t in tools] if tools else None
        )

        # Build parameters
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

        # Additional OpenAI-compatible parameters
        for key in (
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
            "response_format",
        ):
            if key in kwargs:
                params[key] = kwargs[key]

        # Call Groq API
        completion: ChatCompletion = await client.chat.completions.create(
            **params
        )

        choice = completion.choices[0]
        message = choice.message

        # Parse tool calls if present
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
        """Stream LLM completion via Groq API."""
        client = self._get_client()

        # Serialize typed objects to dicts for Groq client
        raw_messages = self._normalize_messages(messages)

        # Build parameters
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
        }

        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        if raw_tools:
            params["tools"] = raw_tools
            params["tool_choice"] = kwargs.get("tool_choice", "auto")

        # Additional parameters
        for key in ("top_p", "frequency_penalty", "presence_penalty", "stop"):
            if key in kwargs:
                params[key] = kwargs[key]

        # Stream from Groq API
        groq_stream = await client.chat.completions.create(**params)

        async for chunk in groq_stream:
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            # Parse delta content
            content = delta.content if delta.content else None

            # Parse tool calls from delta
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
                    )
                    for tc in delta.tool_calls
                ]

            # Parse usage if present (usually in final chunk)
            # Groq may report usage at top-level or under x_groq
            usage = None
            groq_usage = getattr(chunk, "usage", None)
            if not groq_usage:
                x_groq = getattr(chunk, "x_groq", None)
                if x_groq:
                    groq_usage = getattr(x_groq, "usage", None)
            if groq_usage:
                usage = Usage(
                    prompt_tokens=groq_usage.prompt_tokens,
                    completion_tokens=groq_usage.completion_tokens,
                    total_tokens=groq_usage.total_tokens,
                )

            yield StreamChunk(
                delta=Delta(
                    content=content,
                    tool_calls=tool_calls,
                ),
                usage=usage,
                finish_reason=choice.finish_reason,
            )

    async def list_models(self) -> list[str]:
        """List available models from Groq API.

        Returns:
            List of model identifiers

        Note:
            This provides runtime model discovery in addition to
            the static models defined in ai.yaml.
        """
        try:
            client = self._get_client()
            models_page = await client.models.list()

            # Extract model IDs
            models = [model.id for model in models_page.data]
            return models
        except Exception as e:
            logger.warning(f"Failed to list Groq models: {e}")
            # Fallback to static list
            return self.supported_models

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Return metadata for a single model.

        Args:
            model: Model identifier

        Returns:
            Model metadata dict
        """
        # Model info is primarily defined in ai.yaml
        # This provides a fallback for unknown models
        return {
            "model": model,
            "provider": self.provider_name,
            "context_window": 8192,  # Conservative default
            "max_output_tokens": 8192,
        }
