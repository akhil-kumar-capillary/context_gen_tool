"""ToolRegistry — decorator-based tool registration with automatic JSON Schema generation.

Inspired by MCP's `@mcp_server.tool` pattern, but uses native LLM tool_use format
(Anthropic tool_use / OpenAI function_calling) — no transport overhead.

Usage:
    from app.services.tools.registry import registry

    @registry.tool(
        name="list_contexts",
        description="List all context documents for the current organization.",
        module="context_management",
        requires_permission=("context_management", "view"),
        annotations={"display": "Fetching contexts..."},
    )
    async def list_contexts(ctx: ToolContext) -> str:
        ...
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, get_type_hints

from app.services.tools.tool_context import ToolContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type → JSON Schema mapping
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[type, dict] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    list: {"type": "array"},
    dict: {"type": "object"},
}


def _python_type_to_json_schema(tp: type) -> dict:
    """Convert a Python type hint to JSON Schema."""
    # Handle Optional[X] → {type: X} (we don't mark nullable — LLM should always provide)
    origin = getattr(tp, "__origin__", None)

    # typing.Union (Optional is Union[X, None])
    if origin is type(None):
        return {"type": "string"}

    # Handle Union / Optional
    args = getattr(tp, "__args__", None)
    if origin is type(None):
        return {"type": "string"}

    # Optional[X] = Union[X, None]
    import typing
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _python_type_to_json_schema(non_none[0])
        # Multi-type union, fall back to string
        return {"type": "string"}

    # list[X]
    if origin is list:
        if args:
            return {"type": "array", "items": _python_type_to_json_schema(args[0])}
        return {"type": "array"}

    # dict[str, X]
    if origin is dict:
        return {"type": "object"}

    # Literal types
    if origin is typing.Literal:
        return {"type": "string", "enum": list(args)}

    # Direct type match
    if tp in _TYPE_MAP:
        return _TYPE_MAP[tp]

    # Pydantic model → use its JSON schema
    if hasattr(tp, "model_json_schema"):
        return tp.model_json_schema()

    # Fallback
    return {"type": "string"}


def _generate_parameters_schema(func: Callable, skip_ctx: bool = True) -> dict:
    """Auto-generate JSON Schema from function signature.

    Skips the first parameter if it's typed as ToolContext (injected at runtime,
    not visible to the LLM).
    """
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        # Skip ToolContext — it's injected, not an LLM-visible parameter
        if skip_ctx and hints.get(name) is ToolContext:
            continue

        # Skip **kwargs, *args
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        tp = hints.get(name, str)
        schema = _python_type_to_json_schema(tp)

        # Add description from docstring param lines if available
        doc = func.__doc__ or ""
        for line in doc.split("\n"):
            stripped = line.strip()
            if stripped.startswith(f"{name}:") or stripped.startswith(f"{name} :"):
                desc = stripped.split(":", 1)[1].strip()
                schema["description"] = desc
                break

        properties[name] = schema

        # Parameter is required unless it has a default value
        if param.default is inspect.Parameter.empty:
            # Check if it's Optional (then not required)
            origin = getattr(tp, "__origin__", None)
            import typing
            args = getattr(tp, "__args__", None)
            is_optional = (
                origin is typing.Union
                and args
                and type(None) in args
            )
            if not is_optional:
                required.append(name)

    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


# ---------------------------------------------------------------------------
# ToolDefinition dataclass
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    """A registered tool that the LLM can invoke."""

    name: str
    description: str
    handler: Callable[..., Awaitable[str]]
    parameters_schema: dict
    module: str = "general"
    requires_permission: tuple[str, str] | None = None
    annotations: dict = field(default_factory=dict)

    # -- Output formats for different LLM providers --

    def to_anthropic(self) -> dict:
        """Anthropic Messages API tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters_schema,
        }

    def to_openai(self) -> dict:
        """OpenAI Chat Completions function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


# ---------------------------------------------------------------------------
# ToolRegistry — singleton that collects all tools
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Collect and manage tool definitions. Singleton instance at module level."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    # -- Decorator --

    def tool(
        self,
        name: str,
        description: str,
        module: str = "general",
        requires_permission: tuple[str, str] | None = None,
        annotations: dict | None = None,
    ) -> Callable:
        """Register an async function as an LLM-callable tool.

        Example:
            @registry.tool(
                name="list_contexts",
                description="List all context documents.",
                module="context_management",
                requires_permission=("context_management", "view"),
            )
            async def list_contexts(ctx: ToolContext) -> str: ...
        """

        def decorator(func: Callable[..., Awaitable[str]]) -> Callable:
            params = _generate_parameters_schema(func)
            defn = ToolDefinition(
                name=name,
                description=description,
                handler=func,
                parameters_schema=params,
                module=module,
                requires_permission=requires_permission,
                annotations=annotations or {},
            )
            self._tools[name] = defn
            logger.info(f"Registered tool: {name} (module={module})")
            return func

        return decorator

    # -- Lookups --

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def get_all_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get_tools_by_module(self, module: str) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if t.module == module]

    # -- Bulk format conversions --

    def get_tools_for_anthropic(
        self, tools: list[ToolDefinition] | None = None,
    ) -> list[dict]:
        """Return all (or specified) tools in Anthropic API format."""
        source = tools if tools is not None else self.get_all_tools()
        return [t.to_anthropic() for t in source]

    def get_tools_for_openai(
        self, tools: list[ToolDefinition] | None = None,
    ) -> list[dict]:
        """Return all (or specified) tools in OpenAI API format."""
        source = tools if tools is not None else self.get_all_tools()
        return [t.to_openai() for t in source]

    # -- Permission-filtered access --

    async def get_permitted_tools(
        self,
        user_id: int,
        is_admin: bool,
        db: Any,
    ) -> list[ToolDefinition]:
        """Return tools the user has permission to use."""
        from app.core.rbac import check_permission

        permitted: list[ToolDefinition] = []
        for tool_def in self._tools.values():
            if tool_def.requires_permission is None:
                permitted.append(tool_def)
                continue
            module, operation = tool_def.requires_permission
            has_perm = await check_permission(user_id, is_admin, module, operation, db)
            if has_perm:
                permitted.append(tool_def)
        return permitted

    # -- Tool execution --

    async def execute_tool(
        self,
        name: str,
        ctx: ToolContext,
        arguments: dict,
    ) -> str:
        """Execute a tool by name with the given arguments.

        Returns the tool's string result, or an error string.
        """
        tool_def = self.get_tool(name)
        if not tool_def:
            return f"Error: Unknown tool '{name}'"

        # Permission check
        if tool_def.requires_permission:
            from app.core.rbac import check_permission
            module, operation = tool_def.requires_permission
            has_perm = await check_permission(
                ctx.user_id, ctx.is_admin, module, operation, ctx.db,
            )
            if not has_perm:
                return (
                    f"Permission denied: You don't have '{module}.{operation}' "
                    f"permission to use the '{name}' tool."
                )

        try:
            result = await tool_def.handler(ctx, **arguments)
            return str(result)
        except Exception as e:
            logger.exception(f"Tool '{name}' execution failed")
            return f"Error executing '{name}': {str(e)}"

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        tools = ", ".join(self._tools.keys())
        return f"<ToolRegistry tools=[{tools}]>"


# Singleton registry instance — import this everywhere
registry = ToolRegistry()
