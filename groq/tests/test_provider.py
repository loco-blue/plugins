"""Tests for Groq AI provider."""

import pytest
from groq import APIError
from unittest.mock import AsyncMock, MagicMock, patch

from ai.provider import GroqProvider


@pytest.fixture
def provider():
    """Create provider instance with test credentials."""
    provider = GroqProvider()
    provider._credentials = {"api_key": "test-api-key"}
    return provider


@pytest.fixture
def mock_client():
    """Mock API client."""
    client = AsyncMock()
    return client


class TestValidateCredentials:
    """Test credential validation."""

    async def test_validate_success(self, provider):
        """Test successful credential validation."""
        # TODO: Implement test
        # Example:
        # with patch("ai.provider.YourClient") as mock:
        #     mock.return_value.list_models.return_value = []
        #     result = await provider.validate_credentials({"api_key": "valid-key"})
        #     assert result is True
        pytest.skip("Implement credential validation test")

    async def test_validate_missing_key(self, provider):
        """Test validation with missing API key."""
        result = await provider.validate_credentials({})
        assert result is False

    async def test_validate_invalid_key(self, provider):
        """Test validation with invalid API key."""
        # TODO: Implement test
        pytest.skip("Implement invalid key test")


class TestLLMInvoke:
    """Test LLM invoke method."""

    async def test_invoke_basic(self, provider, mock_client):
        """Test basic LLM invocation."""
        # TODO: Implement test
        # Example:
        # with patch("ai.provider.YourClient", return_value=mock_client):
        #     mock_client.chat.completions.create.return_value = MagicMock(
        #         choices=[MagicMock(
        #             message=MagicMock(content="Hello!", tool_calls=None),
        #             finish_reason="stop"
        #         )],
        #         usage=MagicMock(
        #             prompt_tokens=10,
        #             completion_tokens=5,
        #             total_tokens=15
        #         ),
        #         model="test-model"
        #     )
        #
        #     result = await provider.invoke(
        #         model="test-model",
        #         messages=[{"role": "user", "content": "Hi"}]
        #     )
        #
        #     assert result["content"] == "Hello!"
        #     assert result["usage"]["total_tokens"] == 15
        pytest.skip("Implement invoke test")

    async def test_invoke_with_tools(self, provider):
        """Test invocation with function calling."""
        # TODO: Implement tool calling test
        pytest.skip("Implement tool calling test")

    async def test_invoke_with_max_tokens(self, provider):
        """Test invocation with max_tokens parameter."""
        # TODO: Implement max_tokens test
        pytest.skip("Implement max_tokens test")


class TestLLMStream:
    """Test streaming LLM responses."""

    async def test_stream(self, provider):
        """Test streaming response."""
        # TODO: Implement streaming test
        # Example:
        # chunks = []
        # async for chunk in provider.stream(
        #     model="test-model",
        #     messages=[{"role": "user", "content": "Hi"}]
        # ):
        #     chunks.append(chunk)
        #
        # assert len(chunks) > 0
        # assert "delta" in chunks[0]
        pytest.skip("Implement streaming test")


class TestStreamToolHallucination:
    """Groq validates tool-call names server-side and aborts the SSE
    stream with an APIError when the model calls a tool that wasn't in
    request.tools, instead of returning a normal completion. stream()
    must recover from this so the agent's existing unknown-tool
    self-correction path (agent.py) gets a chance to run instead of the
    whole turn failing.
    """

    async def test_recovers_hallucinated_tool_call(self, provider, mock_client):
        """A mid-stream tool-validation APIError yields a synthetic tool
        call instead of propagating, so the caller can self-correct."""

        async def fake_stream():
            raise APIError(
                "tool call validation failed: attempted to call tool "
                "'brute_force' which was not in request.tools",
                request=MagicMock(),
                body=None,
            )
            yield  # pragma: no cover - makes this an async generator

        mock_client.chat.completions.create = AsyncMock(
            return_value=fake_stream()
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            chunks = [
                chunk
                async for chunk in provider.stream(
                    model="llama-3.1-8b-instant",
                    messages=[],
                    tools=[],
                )
            ]

        assert len(chunks) == 1
        tool_calls = chunks[0].delta.tool_calls
        assert tool_calls is not None
        assert tool_calls[0].function.name == "brute_force"

    async def test_reraises_unrelated_api_errors(self, provider, mock_client):
        """Other Groq API errors (rate limit, auth, etc.) must still
        propagate — only the tool-validation abort is recovered from."""

        async def fake_stream():
            raise APIError(
                "rate limit exceeded", request=MagicMock(), body=None
            )
            yield  # pragma: no cover - makes this an async generator

        mock_client.chat.completions.create = AsyncMock(
            return_value=fake_stream()
        )

        with patch.object(provider, "_get_client", return_value=mock_client):
            with pytest.raises(APIError):
                async for _ in provider.stream(
                    model="llama-3.1-8b-instant", messages=[], tools=[]
                ):
                    pass


class TestModelDiscovery:
    """Test model listing and info."""

    async def test_list_models(self, provider):
        """Test listing available models."""
        models = await provider.list_models()
        assert isinstance(models, list)

    async def test_get_model_info(self, provider):
        """Test getting model information."""
        info = await provider.get_model_info("test-model")
        # Returns None if not implemented or model not found
        assert info is None or isinstance(info, dict)
