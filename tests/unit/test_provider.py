from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx2
import pytest

from app.ai.provider import AnthropicProvider, LLMProviderError

# These tests mock the Anthropic SDK client directly - no real network call is made and no
# ANTHROPIC_API_KEY is required.


def _dummy_connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    )


def test_generate_cypher_returns_parsed_output_and_uses_correct_model():
    provider = AnthropicProvider(api_key="test-key")
    provider._client.messages.parse = MagicMock(
        return_value=SimpleNamespace(
            parsed_output=SimpleNamespace(cypher="MATCH (n:Service) RETURN n LIMIT 100")
        )
    )

    result = provider.generate_cypher(
        question="who sends payment-q?", schema_description="<schema>"
    )

    assert result == "MATCH (n:Service) RETURN n LIMIT 100"
    call_kwargs = provider._client.messages.parse.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-8"
    assert "who sends payment-q?" in call_kwargs["messages"][0]["content"]
    assert "<schema>" in call_kwargs["messages"][0]["content"]


def test_generate_cypher_wraps_sdk_errors():
    provider = AnthropicProvider(api_key="test-key")
    provider._client.messages.parse = MagicMock(side_effect=_dummy_connection_error())

    with pytest.raises(LLMProviderError, match="Cypher generation failed"):
        provider.generate_cypher(question="x", schema_description="y")


def test_compose_answer_extracts_text_block():
    provider = AnthropicProvider(api_key="test-key")
    provider._client.messages.create = MagicMock(
        return_value=SimpleNamespace(
            content=[SimpleNamespace(type="text", text="OrderService sends payment-q.")]
        )
    )

    result = provider.compose_answer(
        question="who sends payment-q?", cypher="MATCH (n) RETURN n", rows=[{"a": 1}]
    )

    assert result == "OrderService sends payment-q."
    call_kwargs = provider._client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-8"
    assert "payment-q" in call_kwargs["messages"][0]["content"]


def test_compose_answer_skips_non_text_blocks():
    provider = AnthropicProvider(api_key="test-key")
    provider._client.messages.create = MagicMock(
        return_value=SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text="the real answer"),
            ]
        )
    )

    result = provider.compose_answer(question="x", cypher="MATCH (n) RETURN n", rows=[])
    assert result == "the real answer"


def test_compose_answer_wraps_sdk_errors():
    provider = AnthropicProvider(api_key="test-key")
    provider._client.messages.create = MagicMock(side_effect=_dummy_connection_error())

    with pytest.raises(LLMProviderError, match="Answer composition failed"):
        provider.compose_answer(question="x", cypher="MATCH (n) RETURN n", rows=[])
