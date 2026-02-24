"""LLM service abstraction — supports Anthropic and OpenAI with streaming + tool_use.

Yields event dicts:
  {"type": "chunk", "text": "..."}                         — streamed text content
  {"type": "tool_use_start", "id": "...", "name": "..."}   — tool call detected (params still streaming)
  {"type": "tool_use", "id": "...", "name": "...", "input": {...}}  — tool call complete with params
  {"type": "end", "usage": {...}, "stop_reason": "...", "warning": ...}
"""
import json
import logging
from typing import AsyncGenerator

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cached LLM clients — avoids re-creating httpx connection pools per call.
# Anthropic & OpenAI async clients maintain their own internal httpx pools,
# so caching them means connections are reused across requests.
# Keyed by API key to support per-org override keys in the future.
# ---------------------------------------------------------------------------

_anthropic_clients: dict[str, object] = {}
_openai_clients: dict[str, object] = {}


def _get_anthropic_client(api_key: str | None = None):
    """Get or create a cached Anthropic async client."""
    import anthropic

    key = api_key or settings.anthropic_api_key
    if not key:
        raise ValueError("Anthropic API key not configured")
    if key not in _anthropic_clients:
        _anthropic_clients[key] = anthropic.AsyncAnthropic(api_key=key)
    return _anthropic_clients[key]


def _get_openai_client(api_key: str | None = None):
    """Get or create a cached OpenAI async client."""
    import openai

    key = api_key or settings.openai_api_key
    if not key:
        raise ValueError("OpenAI API key not configured")
    if key not in _openai_clients:
        _openai_clients[key] = openai.AsyncOpenAI(api_key=key)
    return _openai_clients[key]


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


async def stream_anthropic(
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    tools: list[dict] | None = None,
    api_key: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream from Anthropic Claude API with optional tool_use support."""
    client = _get_anthropic_client(api_key)

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    async with client.messages.stream(**kwargs) as stream:
        # Track tool_use blocks being assembled
        current_tool_id = None
        current_tool_name = None
        current_tool_input_json = ""

        async for event in stream:
            # --- Text delta ---
            if event.type == "content_block_start":
                block = event.content_block
                if block.type == "text":
                    if block.text:
                        yield {"type": "chunk", "text": block.text}
                elif block.type == "tool_use":
                    current_tool_id = block.id
                    current_tool_name = block.name
                    current_tool_input_json = ""
                    # Notify immediately that a tool call is being generated
                    yield {"type": "tool_use_start", "id": block.id, "name": block.name}

            elif event.type == "content_block_delta":
                delta = event.delta
                if delta.type == "text_delta":
                    yield {"type": "chunk", "text": delta.text}
                elif delta.type == "input_json_delta":
                    current_tool_input_json += delta.partial_json

            elif event.type == "content_block_stop":
                # If we were accumulating a tool_use block, emit it now
                if current_tool_id and current_tool_name:
                    try:
                        tool_input = json.loads(current_tool_input_json) if current_tool_input_json else {}
                    except json.JSONDecodeError:
                        tool_input = {"_raw": current_tool_input_json}
                    yield {
                        "type": "tool_use",
                        "id": current_tool_id,
                        "name": current_tool_name,
                        "input": tool_input,
                    }
                    current_tool_id = None
                    current_tool_name = None
                    current_tool_input_json = ""

        final = await stream.get_final_message()
        yield {
            "type": "end",
            "usage": {
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
            },
            "stop_reason": final.stop_reason,
            "warning": "Response was truncated" if final.stop_reason == "max_tokens" else None,
        }


async def call_anthropic(
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    tools: list[dict] | None = None,
    api_key: str | None = None,
) -> dict:
    """Non-streaming Anthropic call — used for fast tool-call rounds.

    Returns: {"content": [...blocks...], "usage": {...}, "stop_reason": "..."}
    """
    client = _get_anthropic_client(api_key)

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    response = await client.messages.create(**kwargs)

    result_blocks = []
    for block in response.content:
        if block.type == "text":
            result_blocks.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result_blocks.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })

    return {
        "content": result_blocks,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "stop_reason": response.stop_reason,
    }


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


async def stream_openai(
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    tools: list[dict] | None = None,
    api_key: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream from OpenAI GPT API with optional function-calling support."""
    client = _get_openai_client(api_key)

    full_messages = [{"role": "system", "content": system}] + messages

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "messages": full_messages,
    }
    if tools:
        kwargs["tools"] = tools

    stream = await client.chat.completions.create(**kwargs)

    input_tokens = 0
    output_tokens = 0
    finish_reason = None

    # Accumulate tool calls across streamed chunks
    tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments}

    async for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta.content:
                yield {"type": "chunk", "text": delta.content}

            # Accumulate tool_calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name or "" if tc.function else "",
                            "arguments": "",
                        }
                        # Notify immediately that a tool call is being generated
                        tool_name = tc.function.name if tc.function else ""
                        if tool_name:
                            yield {"type": "tool_use_start", "id": tc.id or "", "name": tool_name}
                    if tc.id:
                        tool_calls_acc[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments

            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

        if chunk.usage:
            input_tokens = chunk.usage.prompt_tokens
            output_tokens = chunk.usage.completion_tokens

    # Emit accumulated tool calls
    for _idx, tc_data in sorted(tool_calls_acc.items()):
        try:
            tool_input = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
        except json.JSONDecodeError:
            tool_input = {"_raw": tc_data["arguments"]}
        yield {
            "type": "tool_use",
            "id": tc_data["id"],
            "name": tc_data["name"],
            "input": tool_input,
        }

    yield {
        "type": "end",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
        "stop_reason": finish_reason,
        "warning": "Response was truncated" if finish_reason == "length" else None,
    }


async def call_openai(
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    tools: list[dict] | None = None,
    api_key: str | None = None,
) -> dict:
    """Non-streaming OpenAI call — used for fast tool-call rounds.

    Returns: {"content": [...blocks...], "usage": {...}, "stop_reason": "..."}
    """
    client = _get_openai_client(api_key)

    full_messages = [{"role": "system", "content": system}] + messages

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": full_messages,
    }
    if tools:
        kwargs["tools"] = tools

    response = await client.chat.completions.create(**kwargs)
    choice = response.choices[0]

    result_blocks = []
    if choice.message.content:
        result_blocks.append({"type": "text", "text": choice.message.content})

    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            try:
                tool_input = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                tool_input = {"_raw": tc.function.arguments}
            result_blocks.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.function.name,
                "input": tool_input,
            })

    return {
        "content": result_blocks,
        "usage": {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
        },
        "stop_reason": choice.finish_reason,
    }


# ---------------------------------------------------------------------------
# Unified interfaces
# ---------------------------------------------------------------------------


async def stream_llm(
    provider: str,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    tools: list[dict] | None = None,
    api_key: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Unified streaming interface for both providers. Supports tool_use."""
    if provider == "anthropic":
        async for event in stream_anthropic(
            model, system, messages, max_tokens, tools, api_key
        ):
            yield event
    elif provider == "openai":
        async for event in stream_openai(
            model, system, messages, max_tokens, tools, api_key
        ):
            yield event
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def call_llm(
    provider: str,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    tools: list[dict] | None = None,
    api_key: str | None = None,
) -> dict:
    """Unified non-streaming call for both providers. Supports tool_use."""
    if provider == "anthropic":
        return await call_anthropic(model, system, messages, max_tokens, tools, api_key)
    elif provider == "openai":
        return await call_openai(model, system, messages, max_tokens, tools, api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}")
