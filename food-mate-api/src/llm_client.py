"""
LLM 客户端模块，封装 OpenAI SDK 与 LiteLLM Proxy 网关的交互逻辑。
"""

from openai import AsyncOpenAI, OpenAI
from openai.types.chat import ChatCompletionMessage

from src.config import DEFAULT_MODEL, PROXY_BASE_URL, PROXY_MASTER_KEY


def _accumulate_stream_delta(
    delta,
    content_parts: list[str],
    tool_calls_acc: dict[int, dict],
) -> str | None:
    """
    处理单个流式 chunk 的 delta，累积文本与 tool_calls。

    参数:
        delta: OpenAI ChatCompletionChunk 的 delta 对象
        content_parts (list[str]): 已累积的文本片段
        tool_calls_acc (dict[int, dict]): 按 index 累积的 tool_call

    返回:
        str | None: 若有文本 delta 则返回该片段，否则 None
    """
    token: str | None = None
    if delta.content:
        content_parts.append(delta.content)
        token = delta.content

    if delta.tool_calls:
        for tc in delta.tool_calls:
            idx = tc.index
            if idx not in tool_calls_acc:
                tool_calls_acc[idx] = {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                }
            acc = tool_calls_acc[idx]
            if tc.id:
                acc["id"] = tc.id
            if tc.function:
                if tc.function.name:
                    acc["function"]["name"] += tc.function.name
                if tc.function.arguments:
                    acc["function"]["arguments"] += tc.function.arguments
    return token


def _build_assistant_message(
    content_parts: list[str],
    tool_calls_acc: dict[int, dict],
) -> dict:
    """
    根据流式累积结果组装完整 assistant 消息。

    参数:
        content_parts (list[str]): 文本片段列表
        tool_calls_acc (dict[int, dict]): 累积的 tool_calls

    返回:
        dict: OpenAI 格式的 assistant 消息
    """
    assistant_msg: dict = {
        "role": "assistant",
        "content": "".join(content_parts),
    }
    if tool_calls_acc:
        assistant_msg["tool_calls"] = [
            tool_calls_acc[i] for i in sorted(tool_calls_acc)
        ]
    return assistant_msg


class LLMClient:
    """
    LLM 客户端类，封装与 LiteLLM Proxy 网关的通信逻辑。

    支持多模型切换，统一调用 OpenAI 兼容接口，可选启用 function calling。
    同步方法供 CLI 使用，异步方法供 Web SSE 路径使用。
    """

    def __init__(
        self,
        base_url: str = PROXY_BASE_URL,
        api_key: str = PROXY_MASTER_KEY,
        default_model: str = DEFAULT_MODEL,
    ):
        """
        初始化 LLM 客户端

        参数:
            base_url (str): LiteLLM Proxy 网关地址，默认读取配置
            api_key (str): 网关鉴权密钥，默认读取配置
            default_model (str): 默认使用的模型名称，默认读取配置
        """
        self.default_model = default_model
        self._base_url = base_url
        self._api_key = api_key
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._async_client: AsyncOpenAI | None = None

    def _get_async_client(self) -> AsyncOpenAI:
        """
        懒加载异步 OpenAI 客户端。

        返回:
            AsyncOpenAI: 异步客户端实例
        """
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                base_url=self._base_url, api_key=self._api_key
            )
        return self._async_client

    def _build_kwargs(
        self,
        messages: list[dict],
        model: str | None,
        tools: list | None,
        *,
        stream: bool = False,
    ) -> dict:
        """
        组装 chat.completions.create 的请求参数。

        参数:
            messages (list[dict]): 消息列表
            model (str | None): 模型名
            tools (list | None): 工具 schema
            stream (bool): 是否流式

        返回:
            dict: 请求 kwargs
        """
        kwargs: dict = {
            "model": model or self.default_model,
            "messages": messages,
        }
        if stream:
            kwargs["stream"] = True
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return kwargs

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        tools: list | None = None,
    ) -> ChatCompletionMessage:
        """
        调用 LLM 进行一次对话补全

        参数:
            messages (list[dict]): OpenAI 格式的消息列表
            model (str | None): 模型名称，为 None 时使用实例默认模型
            tools (list | None): 可选的工具 schema 列表，传入则启用 function calling

        返回:
            ChatCompletionMessage: 模型返回的 message 对象（可能含 tool_calls）
        """
        kwargs = self._build_kwargs(messages, model, tools)
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message

    def chat_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        tools: list | None = None,
    ):
        """
        流式调用 LLM，逐块 yield 文本 delta。

        参数:
            messages (list[dict]): OpenAI 格式消息列表
            model (str | None): 模型名称
            tools (list | None): 工具 schema（流式最终回复时不传 tools）

        Yields:
            str: 每个 token 文本片段
        """
        for event in self.chat_stream_events(messages, model=model, tools=tools):
            if event["type"] == "token":
                yield event["content"]

    def chat_stream_events(
        self,
        messages: list[dict],
        model: str | None = None,
        tools: list | None = None,
    ):
        """
        流式调用 LLM，逐块 yield 文本 delta，并在流结束后 yield 完整 assistant 消息。

        参数:
            messages (list[dict]): OpenAI 格式消息列表
            model (str | None): 模型名称
            tools (list | None): 可选工具 schema，传入则启用 function calling

        Yields:
            dict: {"type": "token", "content": str} 或
                  {"type": "message", "message": dict}
        """
        kwargs = self._build_kwargs(messages, model, tools, stream=True)
        stream = self._client.chat.completions.create(**kwargs)
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict] = {}

        for chunk in stream:
            if not chunk.choices:
                continue
            token = _accumulate_stream_delta(
                chunk.choices[0].delta, content_parts, tool_calls_acc
            )
            if token:
                yield {"type": "token", "content": token}

        yield {
            "type": "message",
            "message": _build_assistant_message(content_parts, tool_calls_acc),
        }

    async def achat_stream_events(
        self,
        messages: list[dict],
        model: str | None = None,
        tools: list | None = None,
    ):
        """
        异步流式调用 LLM，逐块 yield 文本 delta，流结束后 yield 完整 assistant 消息。

        参数:
            messages (list[dict]): OpenAI 格式消息列表
            model (str | None): 模型名称
            tools (list | None): 可选工具 schema，传入则启用 function calling

        Yields:
            dict: {"type": "token", "content": str} 或
                  {"type": "message", "message": dict}
        """
        kwargs = self._build_kwargs(messages, model, tools, stream=True)
        client = self._get_async_client()
        stream = await client.chat.completions.create(**kwargs)
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            token = _accumulate_stream_delta(
                chunk.choices[0].delta, content_parts, tool_calls_acc
            )
            if token:
                yield {"type": "token", "content": token}

        yield {
            "type": "message",
            "message": _build_assistant_message(content_parts, tool_calls_acc),
        }
