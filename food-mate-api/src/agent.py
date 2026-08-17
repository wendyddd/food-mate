"""
FoodMate Agent 核心，组装系统提示与记忆，驱动 LLM 与工具调用循环。
"""

import asyncio
import logging
import time
from types import SimpleNamespace

from src.app_settings import get_rag_mode_enabled
from src.config import DEFAULT_MODEL
from src.llm_client import LLMClient
from src.memory import entries_to_context, list_entries
from src.memory_retriever import retrieve_relevant_memories
from src.memory_schema import MemoryEntry
from src.prompts import build_agent_system_prompt
from src.tool_context import clear_tool_context, set_tool_context
from src.tools import registry

# 单轮对话中工具调用的最大循环次数，防止无限循环
MAX_TOOL_ITERATIONS = 8

logger = logging.getLogger(__name__)


def _resolve_turn_memory_context(
    uid: str,
    user_input: str,
    history: list[dict],
    *,
    model: str,
) -> tuple[str, str, list[MemoryEntry]]:
    """
    按 rag_mode 决定本轮注入的记忆上下文与召回模式。

    参数:
        uid (str): 用户 ID
        user_input (str): 当前用户消息
        history (list[dict]): 不含 system 的历史
        model (str): 召回所用模型

    返回:
        tuple[str, str, list[MemoryEntry]]:
            (memory_context, recall_mode, injected_entries)
            recall_mode 为 full | filtered | full_fallback
    """
    if not get_rag_mode_enabled():
        entries = list_entries(uid)
        return entries_to_context(entries), "full", entries

    result = retrieve_relevant_memories(uid, user_input, history, model=model)
    if not result.ok:
        entries = list_entries(uid)
        return entries_to_context(entries), "full_fallback", entries
    return entries_to_context(result.entries), "filtered", result.entries


def _tool_call_from_dict(tool_call: dict) -> SimpleNamespace:
    """
    将流式累积的 tool_call 字典转为 registry.dispatch 可用的对象。

    参数:
        tool_call (dict): 含 id、function.name、function.arguments 的字典

    返回:
        SimpleNamespace: 与 OpenAI tool_call 结构兼容的对象
    """
    fn = tool_call.get("function") or {}
    return SimpleNamespace(
        id=tool_call.get("id", ""),
        function=SimpleNamespace(
            name=fn.get("name", ""),
            arguments=fn.get("arguments", ""),
        ),
    )


class Agent:
    """
    FoodMate Agent，维护对话历史并处理工具调用循环
    """

    def __init__(self, uid: str, model: str = DEFAULT_MODEL):
        """
        初始化 Agent

        参数:
            uid (str): 已登录用户 ID
            model (str): 使用的模型名称（对应 config.yaml 的 model_name）
        """
        self.uid = uid
        self.model = model
        self.llm = LLMClient(default_model=model)
        # 加载长期记忆并构建系统提示
        self.system_prompt = build_agent_system_prompt(uid)
        # 对话历史，首条为系统提示
        self.messages: list[dict] = [{"role": "system", "content": self.system_prompt}]

    def reset(self) -> None:
        """
        重置对话上下文（保留系统提示与记忆）

        返回:
            None
        """
        self.system_prompt = build_agent_system_prompt(self.uid)
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def reload_memory(self) -> None:
        """
        重新加载长期记忆（user.md），并更新 system prompt。

        适用场景:
            当 user.md 被外部接口（如 Web API）更新后，需要让当前 Agent
            使用最新的长期档案继续对话。

        返回:
            None
        """
        self.system_prompt = build_agent_system_prompt(self.uid)

        # 如果当前对话历史首条为 system，则原地更新内容；否则重置 system 首条。
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = self.system_prompt
        else:
            self.messages = [{"role": "system", "content": self.system_prompt}]

    def set_model(self, model: str) -> None:
        """
        切换当前使用的模型

        参数:
            model (str): 新的模型名称

        返回:
            None
        """
        self.model = model
        self.llm.default_model = model

    def invoke(self, user_input: str, on_tool=None, on_token=None) -> str:
        """
        处理一轮用户输入，执行工具调用循环直至产出最终文本回复

        参数:
            user_input (str): 用户输入文本
            on_tool (callable | None): 可选回调，签名 (tool_name, tool_args_or_result)，
                                       用于在 CLI 中展示工具调用过程
            on_token (callable | None): 可选回调，签名 (token: str)，
                                        用于流式输出每个文本片段

        返回:
            str: Agent 的最终文本回复
        """
        self.messages.append({"role": "user", "content": user_input})

        tools = registry.get_schemas()
        print(f"registry tools: {[tool['function']['name'] for tool in tools]}")

        set_tool_context(self.uid, user_message=user_input)
        try:
            for _ in range(MAX_TOOL_ITERATIONS):
                assistant_msg: dict | None = None
                for event in self.llm.chat_stream_events(self.messages, tools=tools):
                    if event["type"] == "token" and on_token:
                        on_token(event["content"])
                    elif event["type"] == "message":
                        assistant_msg = event["message"]

                if assistant_msg is None:
                    break

                self.messages.append(assistant_msg)
                tool_calls = assistant_msg.get("tool_calls") or []

                # 无工具调用，说明已产出最终回复
                if not tool_calls:
                    return assistant_msg.get("content") or ""

                # 逐个执行工具调用并把结果回灌
                for tc_dict in tool_calls:
                    tc = _tool_call_from_dict(tc_dict)
                    if on_tool:
                        on_tool(tc.function.name, tc.function.arguments)
                    result = registry.dispatch(tc)
                    if on_tool:
                        on_tool(f"{tc.function.name} -> result", result)
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
        finally:
            clear_tool_context()

        # 达到最大循环次数仍未收敛，做兜底回复
        fallback = "(Tool call limit reached. Please add more detail or try a different question.)"
        return fallback

    async def stream_chat_turn(
        self,
        user_input: str,
        history: list[dict],
        *,
        session_id: str | None = None,
    ):
        """
        Web 聊天单轮异步流式处理，yield SSE 事件字典。

        参数:
            user_input (str): 用户输入
            history (list[dict]): 不含 system 的历史消息（user/assistant）
            session_id (str | None): 当前会话 ID，供工具写入记忆时记录来源

        Yields:
            dict: 事件，含 type 及对应字段（token/tool_start/tool_end/done/error）
                done 事件额外含 recall_mode 与 injected_entry_ids
        """
        turn_t0 = time.perf_counter()
        memory_t0 = time.perf_counter()
        memory_context, recall_mode, injected_entries = await asyncio.to_thread(
            _resolve_turn_memory_context,
            self.uid,
            user_input,
            history,
            model=self.model,
        )
        injected_entry_ids = [e.id for e in injected_entries]
        logger.info(
            "stream_chat_turn memory_context uid=%s recall_mode=%s "
            "injected=%d elapsed=%.3fs",
            self.uid,
            recall_mode,
            len(injected_entry_ids),
            time.perf_counter() - memory_t0,
        )

        system_prompt = build_agent_system_prompt(
            self.uid,
            memory_context=memory_context,
            user_message=user_input,
        )
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for msg in history:
            if msg.get("role") in ("user", "assistant"):
                messages.append(
                    {"role": msg["role"], "content": msg.get("content", "")}
                )
        messages.append({"role": "user", "content": user_input})

        tools = registry.get_schemas()
        segments: list[dict] = []
        current_segment: dict = {"content": "", "tool_calls": []}

        set_tool_context(self.uid, session_id=session_id, user_message=user_input)
        try:
            for iteration in range(MAX_TOOL_ITERATIONS):
                assistant_msg: dict | None = None
                llm_t0 = time.perf_counter()
                first_token_at: float | None = None
                token_count = 0

                async for event in self.llm.achat_stream_events(messages, tools=tools):
                    if event["type"] == "token":
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                            logger.info(
                                "stream_chat_turn llm_ttft iteration=%d elapsed=%.3fs",
                                iteration,
                                first_token_at - llm_t0,
                            )
                        token_count += 1
                        current_segment["content"] += event["content"]
                        yield {"type": "token", "content": event["content"]}
                    elif event["type"] == "message":
                        assistant_msg = event["message"]

                llm_elapsed = time.perf_counter() - llm_t0
                tool_calls = (
                    (assistant_msg.get("tool_calls") or []) if assistant_msg else []
                )
                logger.info(
                    "stream_chat_turn llm_done iteration=%d tokens=%d "
                    "tool_calls=%d ttft=%.3fs total=%.3fs",
                    iteration,
                    token_count,
                    len(tool_calls),
                    (first_token_at - llm_t0) if first_token_at else -1.0,
                    llm_elapsed,
                )

                if assistant_msg is None:
                    break

                messages.append(assistant_msg)

                if tool_calls:
                    for tc_dict in tool_calls:
                        tc = _tool_call_from_dict(tc_dict)
                        tool_name = tc.function.name
                        tool_input = tc.function.arguments
                        current_segment["tool_calls"].append(
                            {"tool": tool_name, "input": tool_input}
                        )
                        yield {
                            "type": "tool_start",
                            "tool": tool_name,
                            "input": tool_input,
                        }
                        tool_t0 = time.perf_counter()
                        result = await asyncio.to_thread(registry.dispatch, tc)
                        logger.info(
                            "stream_chat_turn tool_done name=%s elapsed=%.3fs "
                            "output_len=%d",
                            tool_name,
                            time.perf_counter() - tool_t0,
                            len(result or ""),
                        )
                        for item in current_segment["tool_calls"]:
                            if item["tool"] == tool_name and "output" not in item:
                                item["output"] = result
                                break
                        yield {
                            "type": "tool_end",
                            "tool": tool_name,
                            "output": result,
                        }
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": result,
                            }
                        )
                    yield {"type": "new_response"}
                    segments.append(current_segment)
                    current_segment = {"content": "", "tool_calls": []}
                    continue

                segments.append(current_segment)
                full_content = "".join(seg["content"] for seg in segments)
                logger.info(
                    "stream_chat_turn done uid=%s session=%s iterations=%d "
                    "content_len=%d total=%.3fs",
                    self.uid,
                    session_id,
                    iteration + 1,
                    len(full_content),
                    time.perf_counter() - turn_t0,
                )
                yield {
                    "type": "done",
                    "content": full_content,
                    "recall_mode": recall_mode,
                    "injected_entry_ids": injected_entry_ids,
                }
                return

            fallback = "(Tool call limit reached. Please add more detail or try a different question.)"
            current_segment["content"] = fallback
            segments.append(current_segment)
            yield {"type": "token", "content": fallback}
            yield {
                "type": "done",
                "content": fallback,
                "recall_mode": recall_mode,
                "injected_entry_ids": injected_entry_ids,
            }
        except Exception as e:
            logger.exception("stream_chat_turn error uid=%s", self.uid)
            yield {"type": "error", "error": str(e)}
        finally:
            clear_tool_context()
