"""ChatOrchestrator — the core loop tying LLM calls + tool execution + streaming.

Flow:
  1. Call LLM with conversation history + tool definitions
  2. Stream text chunks → forwarded to frontend in real-time
  3. If LLM emits tool_use → execute tool → send result back to LLM
  4. Repeat steps 1-3 (max N rounds) until LLM produces a final text response
"""
import logging
import time
from typing import Callable, Awaitable

from app.config import settings
from app.services.llm_service import stream_llm
from app.services.tools.registry import registry, ToolDefinition
from app.services.tools.tool_context import ToolContext
from app.services.chat_prompts import build_system_prompt

logger = logging.getLogger(__name__)


class ChatOrchestrator:
    """Orchestrate multi-turn LLM + tool-call conversations."""

    def __init__(
        self,
        provider: str,
        model: str,
        tool_context: ToolContext,
        max_tool_rounds: int | None = None,
    ):
        self.provider = provider
        self.model = model
        self.ctx = tool_context
        self.max_tool_rounds = max_tool_rounds or settings.max_tool_rounds

    async def run(
        self,
        messages: list[dict],
        on_text_chunk: Callable[[str], Awaitable[None]],
        on_tool_detected: Callable[[str, str, str], Awaitable[None]],
        on_tool_start: Callable[[str, str, str], Awaitable[None]],
        on_tool_end: Callable[[str, str, str], Awaitable[None]],
        on_end: Callable[[dict], Awaitable[None]],
    ) -> dict:
        """Execute the chat orchestration loop.

        Args:
            messages: Conversation history in LLM message format
            on_text_chunk: Callback(text) for streamed text
            on_tool_detected: Callback(tool_name, tool_id, display) when LLM starts generating a tool call
            on_tool_start: Callback(tool_name, tool_id, display_text) when tool execution begins
            on_tool_end: Callback(tool_name, tool_id, summary) when tool finishes
            on_end: Callback(usage_dict) when generation is complete

        Returns:
            dict with keys:
              - assistant_text: Full accumulated assistant text
              - tool_calls: List of {name, id, input, result} dicts
              - usage: Aggregate {input_tokens, output_tokens}
        """
        # Get permitted tools for this user (opens short-lived DB session internally)
        permitted_tools = await registry.get_permitted_tools(self.ctx)

        # Build tool definitions in the right format
        if self.provider == "anthropic":
            tool_defs = registry.get_tools_for_anthropic(permitted_tools) if permitted_tools else None
        else:
            tool_defs = registry.get_tools_for_openai(permitted_tools) if permitted_tools else None

        # Build system prompt
        tool_names = [t.name for t in permitted_tools]
        system = build_system_prompt(self.ctx.email, self.ctx.org_id, tool_names)

        # Track aggregate state
        all_text = ""
        all_tool_calls: list[dict] = []
        total_usage = {"input_tokens": 0, "output_tokens": 0}

        # Working copy of messages (we append tool results to this)
        working_messages = list(messages)

        for round_num in range(self.max_tool_rounds + 1):
            logger.info(
                f"Chat round {round_num + 1}/{self.max_tool_rounds + 1} "
                f"(provider={self.provider}, model={self.model})"
            )

            # Stream every round so the user always sees real-time progress
            round_text, round_tool_calls, round_usage = await self._stream_round(
                system=system,
                messages=working_messages,
                tools=tool_defs,
                on_text_chunk=on_text_chunk,
                on_tool_detected=on_tool_detected,
            )

            all_text += round_text
            total_usage["input_tokens"] += round_usage.get("input_tokens", 0)
            total_usage["output_tokens"] += round_usage.get("output_tokens", 0)

            if not round_tool_calls:
                # No tool calls — LLM gave a final answer
                break

            # Execute tool calls and build tool results
            assistant_content = self._build_assistant_content(round_text, round_tool_calls)
            working_messages.append({"role": "assistant", "content": assistant_content})

            tool_results_content = []
            for tc in round_tool_calls:
                tool_name = tc["name"]
                tool_id = tc["id"]
                tool_input = tc["input"]

                # Get display annotation
                tool_def = registry.get_tool(tool_name)
                display = (
                    tool_def.annotations.get("display", f"Running {tool_name}...")
                    if tool_def
                    else f"Running {tool_name}..."
                )

                await on_tool_start(tool_name, tool_id, display)

                start = time.time()
                result = await registry.execute_tool(tool_name, self.ctx, tool_input)
                elapsed = time.time() - start

                summary = self._summarize_result(result)
                await on_tool_end(tool_name, tool_id, summary)

                all_tool_calls.append({
                    "name": tool_name,
                    "id": tool_id,
                    "input": tool_input,
                    "result": result,
                    "elapsed_seconds": round(elapsed, 2),
                })

                tool_results_content.append(
                    self._build_tool_result(tool_id, tool_name, result)
                )

            # Append tool results to messages
            if self.provider == "anthropic":
                working_messages.append({
                    "role": "user",
                    "content": tool_results_content,
                })
            else:
                # OpenAI: each tool result is a separate message
                for tr in tool_results_content:
                    working_messages.append(tr)

        # Final callback
        await on_end(total_usage)

        return {
            "assistant_text": all_text,
            "tool_calls": all_tool_calls,
            "usage": total_usage,
        }

    # -----------------------------------------------------------------
    # Internal: streaming round
    # -----------------------------------------------------------------

    async def _stream_round(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None,
        on_text_chunk: Callable[[str], Awaitable[None]],
        on_tool_detected: Callable[[str, str, str], Awaitable[None]],
    ) -> tuple[str, list[dict], dict]:
        """Execute a streaming round. Returns (text, tool_calls, usage)."""
        text = ""
        tool_calls: list[dict] = []
        usage: dict = {}

        async for event in stream_llm(
            provider=self.provider,
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=settings.chat_max_output_tokens,
            tools=tools,
        ):
            if event["type"] == "chunk":
                text += event["text"]
                await on_text_chunk(event["text"])
            elif event["type"] == "tool_use_start":
                # LLM started generating a tool call — notify frontend immediately
                tool_name = event["name"]
                tool_def = registry.get_tool(tool_name)
                display = (
                    tool_def.annotations.get("display", f"Preparing {tool_name}...")
                    if tool_def
                    else f"Preparing {tool_name}..."
                )
                await on_tool_detected(tool_name, event["id"], display)
            elif event["type"] == "tool_use":
                tool_calls.append(event)
            elif event["type"] == "end":
                usage = event.get("usage", {})

        return text, tool_calls, usage

    # -----------------------------------------------------------------
    # Message formatting helpers
    # -----------------------------------------------------------------

    def _build_assistant_content(
        self, text: str, tool_calls: list[dict]
    ) -> list[dict] | str:
        """Build assistant message content block for conversation history."""
        if self.provider == "anthropic":
            blocks = []
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in tool_calls:
                blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })
            return blocks
        else:
            # OpenAI format — tool calls are in a different structure
            # but for message history, we store as text + tool_calls
            return text or ""

    def _build_tool_result(
        self, tool_id: str, tool_name: str, result: str,
    ) -> dict:
        """Build a tool result message for conversation history."""
        if self.provider == "anthropic":
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result,
            }
        else:
            return {
                "role": "tool",
                "tool_call_id": tool_id,
                "content": result,
            }

    def _summarize_result(self, result: str, max_length: int = 100) -> str:
        """Create a short summary of a tool result for the frontend indicator."""
        if not result:
            return "Done"
        # First line, truncated
        first_line = result.split("\n")[0].strip()
        if len(first_line) > max_length:
            return first_line[:max_length] + "..."
        return first_line
