"""
LLM client: wrap OpenAI SDK calls against the LiteLLM Proxy gateway.
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
    Handle one streamed chunk delta: accumulate text and tool_calls.

    Args:
        delta: Delta object from an OpenAI ChatCompletionChunk
        content_parts (list[str]): Accumulated text fragments
        tool_calls_acc (dict[int, dict]): tool_call accumulators keyed by index

    Returns:
        str | None: Text fragment if the delta has content, otherwise None
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
    Build a complete assistant message from streamed accumulators.

    Args:
        content_parts (list[str]): Text fragment list
        tool_calls_acc (dict[int, dict]): Accumulated tool_calls

    Returns:
        dict: Assistant message in OpenAI format
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
    LLM client wrapping communication with the LiteLLM Proxy gateway.

    Supports switching models, a unified OpenAI-compatible API, and optional function calling.
    Sync methods are for CLI; async methods are for the Web SSE path.
    """

    def __init__(
        self,
        base_url: str = PROXY_BASE_URL,
        api_key: str = PROXY_MASTER_KEY,
        default_model: str = DEFAULT_MODEL,
    ):
        """
        Initialize the LLM client.

        Args:
            base_url (str): LiteLLM Proxy gateway URL, default from config
            api_key (str): Gateway auth key, default from config
            default_model (str): Default model name, default from config
        """
        self.default_model = default_model
        self._base_url = base_url
        self._api_key = api_key
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._async_client: AsyncOpenAI | None = None

    def _get_async_client(self) -> AsyncOpenAI:
        """
        Lazily create the async OpenAI client.

        Returns:
            AsyncOpenAI: Async client instance
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
        Build request kwargs for chat.completions.create.

        Args:
            messages (list[dict]): Message list
            model (str | None): Model name
            tools (list | None): Tool schemas
            stream (bool): Whether to stream

        Returns:
            dict: Request kwargs
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
        Call the LLM for one chat completion.

        Args:
            messages (list[dict]): Messages in OpenAI format
            model (str | None): Model name; None uses the instance default
            tools (list | None): Optional tool schemas; if set, enables function calling

        Returns:
            ChatCompletionMessage: Model message (may include tool_calls)
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
        Stream the LLM and yield text deltas chunk by chunk.

        Args:
            messages (list[dict]): Messages in OpenAI format
            model (str | None): Model name
            tools (list | None): Tool schemas (omit tools for a streamed final reply)

        Yields:
            str: Each token text fragment
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
        Stream the LLM, yield text deltas, then yield the full assistant message.

        Args:
            messages (list[dict]): Messages in OpenAI format
            model (str | None): Model name
            tools (list | None): Optional tool schemas; if set, enables function calling

        Yields:
            dict: {"type": "token", "content": str} or
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
        Async stream the LLM, yield text deltas, then yield the full assistant message.

        Args:
            messages (list[dict]): Messages in OpenAI format
            model (str | None): Model name
            tools (list | None): Optional tool schemas; if set, enables function calling

        Yields:
            dict: {"type": "token", "content": str} or
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
