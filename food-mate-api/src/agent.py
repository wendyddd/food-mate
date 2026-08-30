"""
FoodMate Agent core: assemble system prompt and memory, drive the LLM and tool-call loop.
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

# Max tool-call iterations per turn, to prevent infinite loops
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
    Decide this turn's injected memory context and recall mode from rag_mode.

    Args:
        uid (str): User ID
        user_input (str): Current user message
        history (list[dict]): History without system messages
        model (str): Model used for recall

    Returns:
        tuple[str, str, list[MemoryEntry]]:
            (memory_context, recall_mode, injected_entries)
            recall_mode is full | filtered | full_fallback
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
    Convert a streamed tool_call dict into an object usable by registry.dispatch.

    Args:
        tool_call (dict): Dict with id, function.name, and function.arguments

    Returns:
        SimpleNamespace: Object compatible with the OpenAI tool_call shape
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
    FoodMate Agent: keep conversation history and run the tool-call loop.
    """

    def __init__(self, uid: str, model: str = DEFAULT_MODEL):
        """
        Initialize the Agent.

        Args:
            uid (str): Logged-in user ID
            model (str): Model name (matches model_name in config.yaml)
        """
        self.uid = uid
        self.model = model
        self.llm = LLMClient(default_model=model)
        # Load long-term memory and build the system prompt
        self.system_prompt = build_agent_system_prompt(uid)
        # Conversation history; first message is the system prompt
        self.messages: list[dict] = [{"role": "system", "content": self.system_prompt}]

    def reset(self) -> None:
        """
        Reset conversation context (keep system prompt and memory).

        Returns:
            None
        """
        self.system_prompt = build_agent_system_prompt(self.uid)
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def reload_memory(self) -> None:
        """
        Reload long-term memory (user.md) and update the system prompt.

        When to use:
            After user.md is updated by an external API (e.g. Web API), so this
            Agent continues the conversation with the latest long-term profile.

        Returns:
            None
        """
        self.system_prompt = build_agent_system_prompt(self.uid)

        # If the first history message is system, update it in place; otherwise reset it.
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = self.system_prompt
        else:
            self.messages = [{"role": "system", "content": self.system_prompt}]

    def set_model(self, model: str) -> None:
        """
        Switch the model currently in use.

        Args:
            model (str): New model name

        Returns:
            None
        """
        self.model = model
        self.llm.default_model = model

    def invoke(self, user_input: str, on_tool=None, on_token=None) -> str:
        """
        Handle one user turn: run the tool-call loop until a final text reply.

        Args:
            user_input (str): User input text
            on_tool (callable | None): Optional callback, signature
                (tool_name, tool_args_or_result), used to show tool calls in CLI
            on_token (callable | None): Optional callback, signature (token: str),
                used to stream each text chunk

        Returns:
            str: Agent's final text reply
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

                # No tool calls means the final reply is ready
                if not tool_calls:
                    return assistant_msg.get("content") or ""

                # Run each tool call and feed results back into the conversation
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

        # Hit the iteration cap without converging; return a fallback reply
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
        Async streaming handler for one web chat turn; yields SSE event dicts.

        Args:
            user_input (str): User input
            history (list[dict]): History without system messages (user/assistant)
            session_id (str | None): Current session ID, recorded as source when tools write memory

        Yields:
            dict: Event with type and related fields (token/tool_start/tool_end/done/error)
                done events also include recall_mode and injected_entry_ids
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
