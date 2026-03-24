"""
Tests for BedrockClient — format and parse methods.
These tests do NOT require AWS credentials.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from bedrock_client import BedrockClient


# ---------------------------------------------------------------------------
# Helper: create a BedrockClient without calling __init__ (avoids boto3)
# ---------------------------------------------------------------------------

def _make_client():
    """Instantiate BedrockClient without hitting AWS."""
    obj = BedrockClient.__new__(BedrockClient)
    obj.region = "us-east-1"
    obj.model_id = "anthropic.claude-opus-4-20250514"
    obj.client = MagicMock()  # stub out the boto3 client
    return obj


# ===========================================================================
# _format_request tests
# ===========================================================================

class TestFormatRequest:
    def test_basic_structure(self):
        """Request body has anthropic_version, system as list, messages, max_tokens."""
        bc = _make_client()
        messages = [{"role": "user", "content": "Hello"}]
        system = "You are helpful."

        body = bc._format_request(messages, system, tools=[], max_tokens=1024)

        assert body["anthropic_version"] == "bedrock-2023-10-16"
        assert body["system"] == [{"type": "text", "text": "You are helpful."}]
        assert body["messages"] == messages
        assert body["max_tokens"] == 1024

    def test_tools_included_when_non_empty(self):
        """Tools should be present in the body when provided."""
        bc = _make_client()
        tools = [{"name": "my_tool", "description": "does stuff", "input_schema": {"type": "object"}}]

        body = bc._format_request(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=tools,
            max_tokens=2048,
        )

        assert body["tools"] == tools

    def test_tools_omitted_when_empty(self):
        """Tools key should NOT be in the body when tools list is empty."""
        bc = _make_client()

        body = bc._format_request(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=[],
            max_tokens=2048,
        )

        assert "tools" not in body

    def test_tools_omitted_when_none(self):
        """Tools key should NOT be in the body when tools is None."""
        bc = _make_client()

        body = bc._format_request(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=None,
            max_tokens=2048,
        )

        assert "tools" not in body

    def test_messages_pass_through(self):
        """Messages should be passed through unchanged."""
        bc = _make_client()
        messages = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "Thanks"},
        ]

        body = bc._format_request(messages, system="sys", tools=[], max_tokens=512)

        assert body["messages"] is messages  # exact same object, not a copy

    def test_max_tokens_forwarded(self):
        """max_tokens value should be forwarded exactly."""
        bc = _make_client()

        body = bc._format_request(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=[],
            max_tokens=8192,
        )

        assert body["max_tokens"] == 8192


# ===========================================================================
# _parse_response tests
# ===========================================================================

class TestParseResponse:
    def test_text_response(self):
        """Parse a simple text response."""
        bc = _make_client()
        raw = {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello there!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

        result = bc._parse_response(raw)

        assert result["id"] == "msg_123"
        assert result["role"] == "assistant"
        assert result["content"] == [{"type": "text", "text": "Hello there!"}]
        assert result["stop_reason"] == "end_turn"
        assert result["usage"] == {"input_tokens": 10, "output_tokens": 5}

    def test_tool_use_response(self):
        """Parse a response containing a tool_use block."""
        bc = _make_client()
        raw = {
            "id": "msg_456",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me run that tool."},
                {
                    "type": "tool_use",
                    "id": "toolu_789",
                    "name": "execute_tool",
                    "input": {"tool": "nmap", "__raw_args__": "-sV target.com"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 50, "output_tokens": 30},
        }

        result = bc._parse_response(raw)

        assert result["id"] == "msg_456"
        assert result["stop_reason"] == "tool_use"
        assert len(result["content"]) == 2
        assert result["content"][0]["type"] == "text"
        assert result["content"][1]["type"] == "tool_use"
        assert result["content"][1]["name"] == "execute_tool"
        assert result["content"][1]["input"]["tool"] == "nmap"

    def test_multiple_text_blocks(self):
        """Parse a response with multiple text blocks."""
        bc = _make_client()
        raw = {
            "id": "msg_multi",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "First part."},
                {"type": "text", "text": "Second part."},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 10},
        }

        result = bc._parse_response(raw)

        assert len(result["content"]) == 2
        assert result["content"][0]["text"] == "First part."
        assert result["content"][1]["text"] == "Second part."

    def test_missing_optional_fields(self):
        """Parse handles missing optional fields gracefully."""
        bc = _make_client()
        raw = {
            "content": [{"type": "text", "text": "hi"}],
            "stop_reason": "end_turn",
        }

        result = bc._parse_response(raw)

        assert result["id"] is None
        assert result["role"] == "assistant"
        assert result["content"] == [{"type": "text", "text": "hi"}]
        assert result["usage"] == {}


# ===========================================================================
# invoke tests (mocked boto3)
# ===========================================================================

class TestInvoke:
    def test_invoke_calls_boto3_and_parses(self):
        """invoke() should call invoke_model and return parsed response."""
        bc = _make_client()

        fake_response_body = {
            "id": "msg_001",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "pong"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 3, "output_tokens": 1},
        }

        # Mock the boto3 invoke_model return value
        bc.client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=json.dumps(fake_response_body).encode()))
        }

        result = bc.invoke(
            messages=[{"role": "user", "content": "ping"}],
            system="You are a test bot.",
            tools=[],
        )

        # Check that invoke_model was called correctly
        bc.client.invoke_model.assert_called_once()
        call_kwargs = bc.client.invoke_model.call_args[1]
        assert call_kwargs["modelId"] == "anthropic.claude-opus-4-20250514"
        assert call_kwargs["contentType"] == "application/json"
        assert call_kwargs["accept"] == "application/json"

        # Verify the request body sent to boto3
        sent_body = json.loads(call_kwargs["body"])
        assert sent_body["anthropic_version"] == "bedrock-2023-10-16"
        assert sent_body["messages"] == [{"role": "user", "content": "ping"}]

        # Verify parsed result
        assert result["id"] == "msg_001"
        assert result["content"][0]["text"] == "pong"
        assert result["stop_reason"] == "end_turn"


# ===========================================================================
# invoke_stream tests (mocked boto3)
# ===========================================================================

class TestInvokeStream:
    def test_invoke_stream_yields_events(self):
        """invoke_stream() should yield parsed event dicts from the stream."""
        bc = _make_client()

        # Simulate the streaming event structure from Bedrock
        events = [
            {"chunk": {"bytes": json.dumps({"type": "message_start", "message": {"id": "msg_s1", "role": "assistant"}}).encode()}},
            {"chunk": {"bytes": json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}).encode()}},
            {"chunk": {"bytes": json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}).encode()}},
            {"chunk": {"bytes": json.dumps({"type": "content_block_stop", "index": 0}).encode()}},
            {"chunk": {"bytes": json.dumps({"type": "message_stop"}).encode()}},
        ]

        bc.client.invoke_model_with_response_stream.return_value = {
            "body": events
        }

        collected = list(bc.invoke_stream(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=[],
        ))

        assert len(collected) == 5
        assert collected[0]["type"] == "message_start"
        assert collected[2]["type"] == "content_block_delta"
        assert collected[2]["delta"]["text"] == "Hello"
        assert collected[4]["type"] == "message_stop"

        # Verify invoke_model_with_response_stream was called
        bc.client.invoke_model_with_response_stream.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
