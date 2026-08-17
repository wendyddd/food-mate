"""
工具注册中心，实现 注册 -> schema 生成 -> tool_call 解析 -> 工具执行 的完整闭环。
"""

import json
from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    """
    工具定义数据结构

    属性:
        name (str): 工具名称（function calling 中的唯一标识）
        description (str): 工具功能描述，供模型理解何时调用
        parameters (dict): JSON Schema 格式的参数定义
        func (Callable): 实际执行的回调函数
    """

    name: str
    description: str
    parameters: dict
    func: Callable


class ToolRegistry:
    """
    工具注册中心，统一管理所有已注册工具
    """

    def __init__(self):
        """
        初始化注册中心，内部用字典保存工具
        """
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, parameters: dict) -> Callable:
        """
        以装饰器形式注册一个工具

        参数:
            name (str): 工具名称
            description (str): 工具描述
            parameters (dict): JSON Schema 参数定义

        返回:
            Callable: 装饰器，用于包装具体执行函数
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
        生成 OpenAI function calling 所需的 tools schema 数组

        返回:
            list[dict]: 符合 OpenAI 规范的工具 schema 列表
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
        解析模型返回的 tool_call 并执行对应工具

        参数:
            tool_call: OpenAI 返回的单个 tool_call 对象，含 function.name 与 function.arguments

        返回:
            str: 工具执行结果（字符串形式，便于回灌给模型）
        """
        name = tool_call.function.name
        raw_args = tool_call.function.arguments or "{}"

        # 解析 JSON 参数，失败则返回错误信息
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return f"[工具参数解析失败] {name}: {e}"

        tool = self._tools.get(name)
        if tool is None:
            return f"[未知工具] {name}"

        # 执行工具并捕获异常，保证 Agent 循环不被中断
        try:
            result = tool.func(**args)
            return str(result)
        except Exception as e:
            return f"[工具执行异常] {name}: {e}"

    def has_tools(self) -> bool:
        """
        判断是否已注册任何工具

        返回:
            bool: True 表示存在已注册工具
        """
        return bool(self._tools)


# 全局唯一注册中心实例
registry = ToolRegistry()
