"""Groq AI provider plugin.

Provides fast AI inference via Groq LPU™ technology.
Uses official Groq Python client.
"""

import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from groq import APIError, AsyncGroq

from loco_sdk import OpenAICompatiblePlugin
from loco_sdk.types import Delta, FunctionCall, Message, StreamChunk, ToolCall, Usage

logger = logging.getLogger(__name__)

# Groq validates tool-call names server-side and aborts the SSE stream
# mid-generation with this message when the model hallucinates a tool
# that wasn't declared in request.tools.
_HALLUCINATED_TOOL_RE = re.compile(
    r"attempted to call tool '([^']+)' which was not in request\.tools"
)


class GroqProvider(OpenAICompatiblePlugin):
    """Groq AI provider supporting fast LLM inference.

    `invoke`/`validate_credentials`/`list_models`/`get_model_info` all come
    from `OpenAICompatiblePlugin` unchanged — Groq's `AsyncGroq` client
    exposes the same `.chat.completions.create(**params)` /
    `choices[0].message` shape as `AsyncOpenAI`, even though it's a
    different SDK package. `stream()` is overridden here because Groq's
    streaming response has two real quirks the shared default doesn't
    handle: usage is reported under `x_groq` instead of a trailing
    `stream_options` chunk (so Groq's params never set that option), and a
    hallucinated tool call aborts the SSE stream with a distinct
    `APIError` this plugin recovers from instead of propagating.

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
    default_context_window = 8192
    default_max_output_tokens = 8192

    def _get_client(self) -> AsyncGroq:
        """Create Groq client instance.

        Returns:
            Configured AsyncGroq client
        """
        api_key = self._credentials.get("api_key", "")
        base_url = self._credentials.get("base_url")

        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "http_client": httpx.AsyncClient(verify=False),
        }
        if base_url:
            kwargs["base_url"] = base_url

        return AsyncGroq(**kwargs)

    async def stream(
        self,
        model: str,
        messages: list[Message],
        **kwargs: Any,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream LLM completion via Groq API.

        Diverges from the shared default in exactly the two ways Groq's
        API does: no `stream_options` (Groq doesn't support it, so usage
        is read from `x_groq` instead), and a try/except around a
        hallucinated-tool-call abort. Everything else — message
        normalization, param building, tool-call-delta parsing — reuses
        the base class.
        """
        client = self._get_client()

        raw_messages = self._normalize_messages(messages)
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens")
        tools = kwargs.get("tools")
        params = self._build_params(
            model,
            raw_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            stream=True,
            **kwargs,
        )

        groq_stream = await client.chat.completions.create(**params)

        try:
            async for chunk in groq_stream:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                content = delta.content if delta.content else None
                # Groq's delta tool calls carry no `.index` — passing
                # `with_index=False` keeps that field `None` rather than
                # raising on the missing attribute.
                tool_calls = self._parse_delta_tool_calls(
                    delta.tool_calls, with_index=False
                )

                # Groq may report usage at top-level or under x_groq.
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
        except APIError as e:
            match = _HALLUCINATED_TOOL_RE.search(str(e))
            if not match:
                raise
            hallucinated_name = match.group(1)
            logger.warning(
                "Groq aborted stream: model called unregistered tool %r",
                hallucinated_name,
            )
            # Surface it as a normal tool call so the agent loop's
            # existing "unknown tool" handling can feed the rejection
            # back to the model instead of failing the whole turn.
            yield StreamChunk(
                delta=Delta(
                    tool_calls=[
                        ToolCall(
                            id="",
                            type="function",
                            function=FunctionCall(
                                name=hallucinated_name, arguments="{}"
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
