"""Tool system — decorator-based tool registration for LLM tool_use.

Usage:
    from app.services.tools import registry, ToolContext

    @registry.tool(name="my_tool", description="Does something")
    async def my_tool(ctx: ToolContext, arg: str) -> str:
        return f"Result for {arg}"
"""
from app.services.tools.registry import registry, ToolRegistry, ToolDefinition
from app.services.tools.tool_context import ToolContext

__all__ = [
    "registry",
    "ToolRegistry",
    "ToolDefinition",
    "ToolContext",
]
