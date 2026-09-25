"""Tests for OpenRouter provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.provider import OpenRouterProvider


@pytest.fixture
def provider():
    """Create provider instance with test credentials."""
    provider = OpenRouterProvider()
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


class TestGetClient:
    """Test client construction, including optional OpenRouter headers."""

    def test_no_optional_headers_by_default(self, provider):
        client = provider._get_client()
        assert client.default_headers.get("HTTP-Referer") is None
        assert client.default_headers.get("X-Title") is None

    def test_optional_headers_are_forwarded(self):
        provider = OpenRouterProvider()
        provider._credentials = {
            "api_key": "test-api-key",
            "http_referer": "https://example.com",
            "app_name": "My App",
        }
        client = provider._get_client()
        assert client.default_headers["HTTP-Referer"] == "https://example.com"
        assert client.default_headers["X-Title"] == "My App"


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
                model="anthropic/claude-5-sonnet",
            )
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.invoke(
                model="anthropic/claude-5-sonnet",
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
                model="openai/gpt-5.4",
            )
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.invoke(
                model="openai/gpt-5.4",
                messages=[],
                tools=[],
            )

        assert result.tool_calls is not None
        assert result.tool_calls[0].function.name == "get_weather"
        assert result.finish_reason == "tool_calls"

    async def test_invoke_free_tier_router_behaves_like_any_model(
        self, provider, mock_client
    ):
        """`openrouter/free` is a real OpenRouter model that auto-routes
        server-side to whichever free model is currently available — the
        provider sends it through the normal chat-completions call with
        no client-side fallback/rotation logic of its own."""
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(content="hi", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=MagicMock(
                    prompt_tokens=3, completion_tokens=1, total_tokens=4
                ),
                model="meta-llama/llama-4.2-70b-instruct",
            )
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.invoke(
                model="openrouter/free",
                messages=[],
            )

        _, kwargs = mock_client.chat.completions.create.call_args
        assert kwargs["model"] == "openrouter/free"
        assert result.content == "hi"


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
                    model="anthropic/claude-5-sonnet",
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
        streaming API (which OpenRouter implements) never includes a
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
                model="anthropic/claude-5-sonnet",
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
                    model="anthropic/claude-5-sonnet",
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
                model="openai/text-embedding-3-small",
                texts=["hello", "world"],
            )

        assert result.embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    async def test_embed_with_dimensions(self, provider, mock_client):
        mock_client.embeddings.create = AsyncMock(
            return_value=MagicMock(data=[MagicMock(embedding=[0.1, 0.2])])
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            await provider.embed(
                model="openai/text-embedding-3-small",
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
                model="cohere/rerank-4-fast",
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
                model="cohere/rerank-4-fast",
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
                    MagicMock(id="anthropic/claude-5-sonnet"),
                    MagicMock(id="openai/gpt-5.4"),
                ]
            )
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            models = await provider.list_models()

        assert models == [
            "anthropic/claude-5-sonnet",
            "openai/gpt-5.4",
        ]

    async def test_list_models_fallback(self, provider, mock_client):
        mock_client.models.list = AsyncMock(side_effect=Exception("network"))

        with patch.object(provider, "_get_client", return_value=mock_client):
            models = await provider.list_models()

        assert models == provider.supported_models

    async def test_get_model_info(self, provider):
        info = provider.get_model_info("anthropic/claude-5-sonnet")
        assert info["model"] == "anthropic/claude-5-sonnet"
        assert info["provider"] == "openrouter"
