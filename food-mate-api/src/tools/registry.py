"""
Tool registry: register → schema generation → tool_call parsing → tool execution.
"""

import json
from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    """
    Tool definition.

    Attributes:
        name (str): tool name (unique id in function calling)
        description (str): what the tool does, so the model knows when to call it
        parameters (dict): parameter definition in JSON Schema
        func (Callable): callback that actually runs
    """

    name: str
    description: str
    parameters: dict
    func: Callable


class ToolRegistry:
    """
    Central registry that manages all registered tools.
    """

    def __init__(self):
        """
        Initialize the registry with an internal dict of tools.
        """
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, parameters: dict) -> Callable:
        """
        Register a tool as a decorator.

        Args:
            name (str): tool name
            description (str): tool description
            parameters (dict): JSON Schema parameter definition

        Returns:
            Callable: decorator wrapping the implementation function
        """

        def decorator(func: Callable) -> Callable:
            self._tools[name] = Tool(
                name=name,
                description=description,
                parameters=parameters,
                func=func,
            )
            return func

        return decorator

    def get_schemas(self) -> list[dict]:
        """
        Build the tools schema array for OpenAI function calling.

        Returns:
            list[dict]: tool schemas in OpenAI format
        """
        schemas = []
        for tool in self._tools.values():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return schemas

    def dispatch(self, tool_call) -> str:
        """
        Parse a model tool_call and run the matching tool.

        Args:
            tool_call: a single OpenAI tool_call with function.name and function.arguments

        Returns:
            str: tool result as a string, for feeding back to the model
        """
        name = tool_call.function.name
        raw_args = tool_call.function.arguments or "{}"

        # Parse JSON arguments; return an error message on failure
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return f"[工具参数解析失败] {name}: {e}"

        tool = self._tools.get(name)
        if tool is None:
            return f"[未知工具] {name}"

        # Run the tool and catch exceptions so the Agent loop is not interrupted
        try:
            result = tool.func(**args)
            return str(result)
        except Exception as e:
            return f"[工具执行异常] {name}: {e}"

    def has_tools(self) -> bool:
        """
        Whether any tools are registered.

        Returns:
            bool: True if at least one tool is registered
        """
        return bool(self._tools)


# Global singleton registry instance
registry = ToolRegistry()
