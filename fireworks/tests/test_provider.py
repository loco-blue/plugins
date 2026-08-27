"""Tests for Fireworks AI provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.provider import FireworksProvider


@pytest.fixture
def provider():
    """Create provider instance with test credentials."""
    provider = FireworksProvider()
    provider._credentials = {"api_key": "test-api-key"}
    return provider


@pytest.fixture
def mock_client():
    """Mock AsyncOpenAI client."""
    client = AsyncMock()
    return client


class TestValidateCredentials:
    """Test credential validation."""

    async def test_validate_missing_key(self, provider):
        result = await provider.validate_credentials({})
        assert result is False

    async def test_validate_success(self, provider, mock_client):
        mock_client.models.list = AsyncMock(return_value=MagicMock())
        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.validate_credentials(
                {"api_key": "valid-key"}
            )
        assert result is True

    async def test_validate_invalid_key(self, provider, mock_client):
        mock_client.models.list = AsyncMock(side_effect=Exception("401"))
        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.validate_credentials(
                {"api_key": "bad-key"}
            )
        assert result is False


class TestLLMInvoke:
    """Test LLM invoke method."""

    async def test_invoke_basic(self, provider, mock_client):
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(content="Hello!", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=MagicMock(
                    prompt_tokens=10, completion_tokens=5, total_tokens=15
                ),
                model="accounts/fireworks/models/gpt-oss-20b",
            )
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.invoke(
                model="accounts/fireworks/models/gpt-oss-20b",
                messages=[],
            )

        assert result.content == "Hello!"
        assert result.usage.total_tokens == 15
        assert result.finish_reason == "stop"

    async def test_invoke_with_tools(self, provider, mock_client):
        tool_call = MagicMock(id="call_1", type="function")
        tool_call.function = MagicMock(arguments='{"city": "SF"}')
        tool_call.function.name = "get_weather"
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(content=None, tool_calls=[tool_call]),
                        finish_reason="tool_calls",
                    )
                ],
                usage=MagicMock(
                    prompt_tokens=20, completion_tokens=8, total_tokens=28
                ),
                model="accounts/fireworks/models/gpt-oss-120b",
            )
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.invoke(
                model="accounts/fireworks/models/gpt-oss-120b",
                messages=[],
                tools=[],
            )

        assert result.tool_calls is not None
        assert result.tool_calls[0].function.name == "get_weather"
        assert result.finish_reason == "tool_calls"


class TestLLMStream:
    """Test streaming LLM responses."""

    async def test_stream(self, provider, mock_client):
        async def fake_stream():
            yield MagicMock(
                choices=[
                    MagicMock(
                        delta=MagicMock(content="Hel", tool_calls=None),
                        finish_reason=None,
                    )
                ],
                usage=None,
            )
            yield MagicMock(
                choices=[
                    MagicMock(
                        delta=MagicMock(content="lo", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=MagicMock(
                    prompt_tokens=5, completion_tokens=2, total_tokens=7
                ),
            )

        mock_client.chat.completions.create = AsyncMock(
            return_value=fake_stream()
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            chunks = [
                chunk
                async for chunk in provider.stream(
                    model="accounts/fireworks/models/gpt-oss-20b",
                    messages=[],
                )
            ]

        assert len(chunks) == 2
        assert chunks[0].delta.content == "Hel"
        assert chunks[1].delta.content == "lo"
        assert chunks[1].finish_reason == "stop"
        assert chunks[1].usage.total_tokens == 7

    async def test_stream_requests_usage_via_stream_options(
        self, provider, mock_client
    ):
        """Without `stream_options={"include_usage": True}`, the OpenAI
        streaming API (which Fireworks implements) never includes a
        `usage` field on any chunk — every chunk's `chunk.usage` is
        `None`, so no LLMResultChunk this method yields ever carries
        real token usage, regardless of how the response is parsed.
        This must be requested explicitly on every streaming call."""

        async def fake_stream():
            yield MagicMock(
                choices=[
                    MagicMock(
                        delta=MagicMock(content="hi", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=None,
            )

        mock_client.chat.completions.create = AsyncMock(
            return_value=fake_stream()
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            async for _ in provider.stream(
                model="accounts/fireworks/models/gpt-oss-20b",
                messages=[],
            ):
                pass

        _, kwargs = mock_client.chat.completions.create.call_args
        assert kwargs.get("stream_options") == {"include_usage": True}

    async def test_stream_yields_the_trailing_usage_only_chunk(
        self, provider, mock_client
    ):
        """With `stream_options.include_usage=True`, the OpenAI-compatible
        API sends token usage on its own FINAL chunk with an empty
        `choices` list (content/finish_reason already sent on the prior
        chunk) — not attached to the last content-bearing chunk. A loop
        that skips every chunk with no `choices` therefore discards the
        only chunk that ever carries usage, silently dropping it every
        time regardless of `stream_options`."""

        async def fake_stream():
            yield MagicMock(
                choices=[
                    MagicMock(
                        delta=MagicMock(content="hi", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=None,
            )
            yield MagicMock(
                choices=[],
                usage=MagicMock(
                    prompt_tokens=5, completion_tokens=2, total_tokens=7
                ),
            )

        mock_client.chat.completions.create = AsyncMock(
            return_value=fake_stream()
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            chunks = [
                chunk
                async for chunk in provider.stream(
                    model="accounts/fireworks/models/gpt-oss-20b",
                    messages=[],
                )
            ]

        usage_chunks = [c for c in chunks if c.usage is not None]
        assert len(usage_chunks) == 1
        assert usage_chunks[0].usage.total_tokens == 7


class TestEmbed:
    """Test embedding generation."""

    async def test_embed_basic(self, provider, mock_client):
        mock_client.embeddings.create = AsyncMock(
            return_value=MagicMock(
                data=[
                    MagicMock(embedding=[0.1, 0.2, 0.3]),
                    MagicMock(embedding=[0.4, 0.5, 0.6]),
                ]
            )
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.embed(
                model="accounts/fireworks/models/nomic-embed-text-v1p5",
                texts=["hello", "world"],
            )

        assert result.embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    async def test_embed_with_dimensions(self, provider, mock_client):
        mock_client.embeddings.create = AsyncMock(
            return_value=MagicMock(data=[MagicMock(embedding=[0.1, 0.2])])
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            await provider.embed(
                model="accounts/fireworks/models/nomic-embed-text-v1p5",
                texts=["hi"],
                dimensions=2,
            )

        _, kwargs = mock_client.embeddings.create.call_args
        assert kwargs["dimensions"] == 2


class TestRerank:
    """Test reranking via the dedicated /v1/rerank endpoint."""

    async def test_rerank_basic(self, provider):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(
            return_value={
                "results": [
                    {"index": 1, "relevance_score": 0.95},
                    {"index": 0, "relevance_score": 0.42},
                ]
            }
        )

        with patch(
            "httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.rerank(
                model="accounts/fireworks/models/qwen3-reranker-8b",
                query="what is the capital of france?",
                documents=["paris is a city", "paris is the capital"],
            )

        assert len(result.results) == 2
        assert result.results[0].index == 1
        assert result.results[0].score == 0.95

    async def test_rerank_with_top_n(self, provider):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"results": []})

        with patch(
            "httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)
        ) as mock_post:
            await provider.rerank(
                model="accounts/fireworks/models/qwen3-reranker-8b",
                query="q",
                documents=["a", "b"],
                top_n=1,
            )

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["top_n"] == 1


class TestModelDiscovery:
    """Test model listing and info."""

    async def test_list_models_success(self, provider, mock_client):
        mock_client.models.list = AsyncMock(
            return_value=MagicMock(
                data=[
                    MagicMock(id="accounts/fireworks/models/gpt-oss-20b"),
                    MagicMock(id="accounts/fireworks/models/gpt-oss-120b"),
                ]
            )
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            models = await provider.list_models()

        assert models == [
            "accounts/fireworks/models/gpt-oss-20b",
            "accounts/fireworks/models/gpt-oss-120b",
        ]

    async def test_list_models_fallback(self, provider, mock_client):
        mock_client.models.list = AsyncMock(side_effect=Exception("network"))

        with patch.object(provider, "_get_client", return_value=mock_client):
            models = await provider.list_models()

        assert models == provider.supported_models

    async def test_get_model_info(self, provider):
        info = provider.get_model_info("accounts/fireworks/models/gpt-oss-20b")
        assert info["model"] == "accounts/fireworks/models/gpt-oss-20b"
        assert info["provider"] == "fireworks"
