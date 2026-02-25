"""LLM service abstraction — supports Anthropic and OpenAI with streaming + tool_use.

Yields event dicts:
  {"type": "chunk", "text": "..."}                         — streamed text content
  {"type": "tool_use_start", "id": "...", "name": "..."}   — tool call detected (params still streaming)
  {"type": "tool_use", "id": "...", "name": "...", "input": {...}}  — tool call complete with params
  {"type": "end", "usage": {...}, "stop_reason": "...", "warning": ...}
"""
import asyncio
import json
import logging
from typing import AsyncGenerator

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cancel-race helper — shared between Anthropic & OpenAI streaming
# ---------------------------------------------------------------------------


async def _next_or_cancel(
    iterator,
    cancel_event: asyncio.Event | None,
    provider: str,
    on_cancel=None,
) -> tuple[bool, object | None]:
    """Race ``iterator.__anext__()`` against *cancel_event*.

    Returns ``(should_break, item)``:
    * ``(True, None)``  — cancelled or stream ended (StopAsyncIteration)
    * ``(False, item)`` — got the next item
    """
    # Quick pre-check
    if cancel_event and cancel_event.is_set():
        logger.info(f"{provider} stream cancelled (pre-check)")
        if on_cancel:
            await on_cancel()
        return True, None

    try:
        if cancel_event:
            next_task = asyncio.ensure_future(iterator.__anext__())
            cancel_task = asyncio.ensure_future(cancel_event.wait())
            done, pending = await asyncio.wait(
                {next_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for p in pending:
                p.cancel()
                try:
                    await p
                except (asyncio.CancelledError, StopAsyncIteration):
                    pass

            if cancel_task in done:
                logger.info(f"{provider} stream cancelled (race)")
                if on_cancel:
                    await on_cancel()
                return True, None

            return False, next_task.result()
        else:
            return False, await iterator.__anext__()
    except StopAsyncIteration:
        return True, None


# ---------------------------------------------------------------------------
# Cached LLM clients — separate instances for streaming vs batch workloads.
#
# Why separate: The Anthropic SDK's AsyncAnthropic has internal retry/backoff
# state. When batch calls (doc generation) hit 429s, their backoff can
# interfere with active streaming connections (chat, refactor). Separate
# instances keep retry state fully isolated.
#
# Keyed by API key to support per-org override keys in the future.
# ---------------------------------------------------------------------------

_anthropic_stream_clients: dict[str, object] = {}
_anthropic_batch_clients: dict[str, object] = {}
_openai_stream_clients: dict[str, object] = {}
_openai_batch_clients: dict[str, object] = {}

# Concurrency limits — prevent one workload type from monopolizing the
# provider's per-key rate limit (tokens-per-minute / requests-per-minute).
_streaming_semaphore = asyncio.Semaphore(3)  # max 3 concurrent streaming calls
_batch_semaphore = asyncio.Semaphore(2)      # max 2 concurrent batch calls


def _get_anthropic_client(api_key: str | None = None, *, streaming: bool = False):
    """Get or create a cached Anthropic async client.

    Streaming and batch workloads use separate client instances so that
    the SDK's retry/backoff state on batch 429s doesn't interfere with
    active streaming connections.
    """
    import anthropic

    key = api_key or settings.anthropic_api_key
    if not key:
        raise ValueError("Anthropic API key not configured")
    cache = _anthropic_stream_clients if streaming else _anthropic_batch_clients
    if key not in cache:
        cache[key] = anthropic.AsyncAnthropic(api_key=key)
    return cache[key]


def _get_openai_client(api_key: str | None = None, *, streaming: bool = False):
    """Get or create a cached OpenAI async client."""
    import openai

    key = api_key or settings.openai_api_key
    if not key:
        raise ValueError("OpenAI API key not configured")
    cache = _openai_stream_clients if streaming else _openai_batch_clients
    if key not in cache:
        cache[key] = openai.AsyncOpenAI(api_key=key)
    return cache[key]


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
    cancel_event: asyncio.Event | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream from Anthropic Claude API with optional tool_use support."""
    async with _streaming_semaphore:
        client = _get_anthropic_client(api_key, streaming=True)

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        cancelled = False
        async with client.messages.stream(**kwargs) as stream:
            # Track tool_use blocks being assembled
            current_tool_id = None
            current_tool_name = None
            current_tool_input_json = ""

            # Manual iteration — race __anext__ against cancel event so
            # cancel_event.set() interrupts mid-await instead of blocking.
            iterator = stream.__aiter__()
            while True:
                should_break, event = await _next_or_cancel(
                    iterator, cancel_event, "Anthropic",
                )
                if should_break:
                    cancelled = cancel_event.is_set() if cancel_event else False
                    break

                # --- Process event ---
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "text":
                        if block.text:
                            yield {"type": "chunk", "text": block.text}
                    elif block.type == "tool_use":
                        current_tool_id = block.id
                        current_tool_name = block.name
                        current_tool_input_json = ""
                        yield {"type": "tool_use_start", "id": block.id, "name": block.name}

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield {"type": "chunk", "text": delta.text}
                    elif delta.type == "input_json_delta":
                        current_tool_input_json += delta.partial_json

                elif event.type == "content_block_stop":
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

            # get_final_message() must be called inside the async with block.
            # Only call it if stream completed naturally — it waits for the
            # full response which would block cancellation.
            if not cancelled:
                try:
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
                except Exception:
                    yield {"type": "end", "usage": {"input_tokens": 0, "output_tokens": 0}, "stop_reason": "error"}

        # If cancelled, yield end event after the context manager has closed the HTTP connection
        if cancelled:
            yield {"type": "end", "usage": {"input_tokens": 0, "output_tokens": 0}, "stop_reason": "cancelled"}


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
    async with _batch_semaphore:
        client = _get_anthropic_client(api_key, streaming=False)

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
    cancel_event: asyncio.Event | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream from OpenAI GPT API with optional function-calling support."""
    async with _streaming_semaphore:
        client = _get_openai_client(api_key, streaming=True)

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
        cancelled = False

        # Accumulate tool calls across streamed chunks
        tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments}

        # Manual iteration — race __anext__ against cancel event
        async def _close_stream():
            try:
                await stream.close()
            except Exception:
                pass

        iterator = stream.__aiter__()
        while True:
            should_break, chunk = await _next_or_cancel(
                iterator, cancel_event, "OpenAI", on_cancel=_close_stream,
            )
            if should_break:
                cancelled = cancel_event.is_set() if cancel_event else False
                break

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

        if not cancelled:
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
            "stop_reason": "cancelled" if cancelled else finish_reason,
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
    async with _batch_semaphore:
        client = _get_openai_client(api_key, streaming=False)

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
    cancel_event: asyncio.Event | None = None,
) -> AsyncGenerator[dict, None]:
    """Unified streaming interface for both providers. Supports tool_use."""
    if provider == "anthropic":
        async for event in stream_anthropic(
            model, system, messages, max_tokens, tools, api_key, cancel_event
        ):
            yield event
    elif provider == "openai":
        async for event in stream_openai(
            model, system, messages, max_tokens, tools, api_key, cancel_event
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
