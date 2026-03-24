"""
AWS Bedrock Runtime wrapper for Claude Messages API.

Replaces anthropic.AsyncAnthropic with IAM-based Bedrock calls.
Auth is handled automatically by boto3 (instance role / env vars).
"""

import json
from typing import Generator, Optional

import boto3


class BedrockClient:
    """Wrapper around AWS Bedrock Runtime for Claude models."""

    def __init__(
        self,
        region: str = "us-east-1",
        model_id: str = "us.anthropic.claude-opus-4-6-v1",
    ):
        self.region = region
        self.model_id = model_id
        self.client = boto3.client("bedrock-runtime", region_name=region)

    def _format_request(
        self,
        messages: list[dict],
        system: str,
        tools: Optional[list[dict]],
        max_tokens: int,
    ) -> dict:
        """Format a request body for Bedrock's Claude Messages API.

        Args:
            messages: Conversation messages (passed through as-is).
            system: System prompt string.
            tools: Tool definitions (omitted from body if empty/None).
            max_tokens: Maximum tokens in response.

        Returns:
            Dict ready to be JSON-serialized and sent to invoke_model.
        """
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "system": [{"type": "text", "text": system}],
            "messages": messages,
            "max_tokens": max_tokens,
        }

        if tools:
            body["tools"] = tools

        return body

    def _parse_response(self, raw: dict) -> dict:
        """Normalize a Bedrock Claude response to a standard dict.

        Args:
            raw: Raw JSON response from Bedrock invoke_model.

        Returns:
            Dict with keys: id, role, content, stop_reason, usage.
        """
        return {
            "id": raw.get("id"),
            "role": raw.get("role", "assistant"),
            "content": raw.get("content", []),
            "stop_reason": raw.get("stop_reason"),
            "usage": raw.get("usage", {}),
        }

    def invoke(
        self,
        messages: list[dict],
        system: str,
        tools: Optional[list[dict]] = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Synchronous call to Claude via Bedrock invoke_model.

        Args:
            messages: Conversation messages.
            system: System prompt.
            tools: Tool definitions (optional).
            max_tokens: Max response tokens.

        Returns:
            Parsed response dict with id, role, content, stop_reason, usage.
        """
        body = self._format_request(messages, system, tools, max_tokens)

        response = self.client.invoke_model(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )

        raw = json.loads(response["body"].read())
        return self._parse_response(raw)

    def invoke_stream(
        self,
        messages: list[dict],
        system: str,
        tools: Optional[list[dict]] = None,
        max_tokens: int = 4096,
    ) -> Generator[dict, None, None]:
        """Streaming call to Claude via Bedrock invoke_model_with_response_stream.

        Args:
            messages: Conversation messages.
            system: System prompt.
            tools: Tool definitions (optional).
            max_tokens: Max response tokens.

        Yields:
            Event dicts from the Bedrock streaming response (message_start,
            content_block_start, content_block_delta, content_block_stop,
            message_stop, etc.).
        """
        body = self._format_request(messages, system, tools, max_tokens)

        response = self.client.invoke_model_with_response_stream(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )

        for event in response["body"]:
            chunk = event.get("chunk")
            if chunk and "bytes" in chunk:
                yield json.loads(chunk["bytes"])
