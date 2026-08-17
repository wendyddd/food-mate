"""
POST /api/chat — SSE 流式对话接口。
"""

import asyncio
import json
import logging
import re
import time
import traceback
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.agent import Agent
from src.api.deps import get_current_user
from src.chat_session import (
    load_history,
    load_history_for_agent,
    save_message,
    update_title,
)
from src.llm_client import LLMClient
from src.memory import get_entries_by_ids
from src.memory_judge import judge_memory_from_turn
from src.user_auth import UserRecord

router = APIRouter()
logger = logging.getLogger(__name__)

CANVAS_TAG = "food-mate-canvas"
MEMORY_JUDGE_TIMEOUT = 30.0


class ChatRequest(BaseModel):
    """聊天请求体。"""

    message: str
    session_id: str = "default"
    stream: bool = True


async def _judge_and_apply_memory(
    uid: str,
    message: str,
    history: list[dict[str, Any]],
    session_id: str,
) -> dict[str, Any]:
    """
    在后台并行执行本轮记忆判断并写入。

    参数:
        uid (str): 用户 ID
        message (str): 用户消息
        history (list): 历史消息
        session_id (str): 当前会话 ID

    返回:
        dict: {changed, added_ids, updated_ids, deleted_ids, entries}
    """
    t0 = time.perf_counter()
    try:
        result = await asyncio.to_thread(
            judge_memory_from_turn,
            message,
            history,
            uid,
            session_id=session_id,
        )
        ar = result.apply_result
        logger.info(
            "memory_judge done uid=%s session=%s changed=%s elapsed=%.3fs",
            uid,
            session_id,
            result.changed,
            time.perf_counter() - t0,
        )
        return {
            "changed": result.changed,
            "added_ids": ar.added_ids,
            "updated_ids": ar.updated_ids,
            "deleted_ids": ar.deleted_ids,
            "entries": [e.to_dict() for e in ar.entries],
        }
    except Exception:
        traceback.print_exc()
        logger.warning(
            "memory_judge failed uid=%s session=%s elapsed=%.3fs",
            uid,
            session_id,
            time.perf_counter() - t0,
        )
        return {
            "changed": False,
            "added_ids": [],
            "updated_ids": [],
            "deleted_ids": [],
            "entries": [],
        }


def _filter_recall_memory_ids(
    injected_ids: list[str],
    memory_result: dict[str, Any] | None,
) -> list[str]:
    """
    从注入记忆 ID 中剔除本轮 Judge 新增/更新的条目，仅保留召回的旧记忆。

    参数:
        injected_ids (list[str]): 本轮注入的全部记忆 ID
        memory_result (dict | None): Judge 返回结果，含 added_ids / updated_ids

    返回:
        list[str]: 可用于「Memories used」展示的记忆 ID
    """
    if not injected_ids:
        return []
    result = memory_result or {}
    exclude = set(result.get("added_ids") or []) | set(result.get("updated_ids") or [])
    return [mid for mid in injected_ids if mid not in exclude]


def _build_memory_refs_from_ids(uid: str, entry_ids: list[str]) -> list[dict[str, str]]:
    """
    按记忆 ID 列表构造前端展示用的引用条目。

    参数:
        uid (str): 用户 ID
        entry_ids (list[str]): 本轮注入或引用的记忆 ID

    返回:
        list[dict]: 引用条目列表
    """
    if not entry_ids:
        return []
    entries = get_entries_by_ids(uid, entry_ids)
    return [
        {
            "id": e.id,
            "category": e.category,
            "content": e.content,
            "source_type": e.source_type,
        }
        for e in entries
    ]


def _generate_title(uid: str, session_id: str) -> str | None:
    """
    根据首轮对话生成会话标题（同步，供 to_thread 调用）。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        str | None: 生成的标题，失败时返回 None
    """
    try:
        messages = load_history(uid, session_id)
        first_user = ""
        first_assistant = ""
        for msg in messages:
            if msg["role"] == "user" and not first_user:
                first_user = msg["content"][:200]
            elif msg["role"] == "assistant" and not first_assistant:
                first_assistant = msg["content"][:200]
            if first_user and first_assistant:
                break
        if not first_user:
            return None

        llm = LLMClient()
        prompt = (
            "Based on the conversation below, generate a short session title (max 10 words). "
            "Use the same language as the user message. "
            "Output only the title text, no quotes or punctuation.\n\n"
            f"User: {first_user}\n"
            f"Assistant: {first_assistant}"
        )
        result = llm.chat([{"role": "user", "content": prompt}])
        title = (result.content or "").strip().strip("\"'''")[:40]
        if title:
            update_title(uid, session_id, title)
        return title or None
    except Exception:
        traceback.print_exc()
        return None


def _parse_suggested_questions(raw: str) -> list[str]:
    """
    从模型输出中解析追问列表（优先 JSON 数组，否则按行拆分）。

    参数:
        raw (str): 模型原始输出

    返回:
        list[str]: 最多 3 条非空追问
    """
    text = (raw or "").strip()
    if not text:
        return []

    # 尝试提取 JSON 数组
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, list):
                questions = [
                    str(q).strip().strip("\"'").lstrip("0123456789.-、)） ").strip()
                    for q in parsed
                    if str(q).strip()
                ]
                return questions[:3]
        except (json.JSONDecodeError, TypeError):
            pass

    # 按行拆分，去掉编号前缀
    questions: list[str] = []
    for line in text.splitlines():
        line = line.strip().strip("\"'").lstrip("0123456789.-、)） ").strip()
        if line:
            questions.append(line)
        if len(questions) >= 3:
            break
    return questions[:3]


def _generate_suggested_questions(
    user_message: str, assistant_content: str
) -> list[str]:
    """
    根据本轮对话生成约 3 条可继续追问的短问题（同步，供 to_thread 调用）。

    参数:
        user_message (str): 用户本轮消息
        assistant_content (str): 助手本轮完整回复

    返回:
        list[str]: 追问列表，失败时返回空列表
    """
    try:
        user_snip = (user_message or "")[:300]
        asst_snip = (assistant_content or "")[:500]
        if not user_snip or not asst_snip:
            return []

        llm = LLMClient()
        from src.prompts import has_cjk

        lang_rule = (
            "Use the same language as the user message. "
            "Each question should be concise (under 30 characters for Chinese, under 12 words for English). "
        )
        if not has_cjk(user_snip):
            lang_rule = (
                "The user message is in English. All 3 questions MUST be English only — "
                "no Chinese or other non-English scripts. "
                "Each question should be concise (under 12 words). "
            )
        prompt = (
            "Based on the cooking conversation below, suggest exactly 3 short follow-up "
            "questions the user might ask next. "
            f"{lang_rule}"
            "Output ONLY a JSON array of 3 strings, no other text.\n\n"
            f"User: {user_snip}\n"
            f"Assistant: {asst_snip}"
        )
        result = llm.chat([{"role": "user", "content": prompt}])
        return _parse_suggested_questions(result.content or "")
    except Exception:
        traceback.print_exc()
        return []


async def event_generator(
    uid: str,
    message: str,
    session_id: str,
) -> AsyncGenerator[dict, None]:
    """
    从 Agent 流式生成 SSE 事件并持久化会话。

    参数:
        uid (str): 用户 ID
        message (str): 用户消息
        session_id (str): 会话 ID

    Yields:
        dict: SSE 事件 {event, data}
    """
    turn_t0 = time.perf_counter()
    try:
        history = load_history_for_agent(uid, session_id)
        is_first_message = len(history) == 0
        logger.info(
            "chat_start uid=%s session=%s history_len=%d msg_len=%d",
            uid,
            session_id,
            len(history),
            len(message),
        )

        # 先完成记忆判断，有变更则先下发 Toast，再开始生成回复
        memory_result: dict[str, Any] = {
            "changed": False,
            "added_ids": [],
            "updated_ids": [],
        }
        memory_task = asyncio.create_task(
            _judge_and_apply_memory(uid, message, history, session_id)
        )
        try:
            wait_t0 = time.perf_counter()
            memory_result = await asyncio.wait_for(
                memory_task, timeout=MEMORY_JUDGE_TIMEOUT
            )
            logger.info(
                "chat_memory_wait uid=%s session=%s changed=%s elapsed=%.3fs",
                uid,
                session_id,
                memory_result.get("changed"),
                time.perf_counter() - wait_t0,
            )
            if memory_result.get("changed"):
                toast_payload = {
                    "changed": memory_result.get("changed"),
                    "added_ids": memory_result.get("added_ids") or [],
                    "updated_ids": memory_result.get("updated_ids") or [],
                    "deleted_ids": memory_result.get("deleted_ids") or [],
                }
                yield {
                    "event": "memory_updated",
                    "data": json.dumps(toast_payload, ensure_ascii=False),
                }
        except asyncio.TimeoutError:
            memory_task.cancel()
            logger.warning("chat_memory_timeout uid=%s session=%s", uid, session_id)
        except Exception:
            traceback.print_exc()

        agent = Agent(uid=uid)
        segments: list[dict] = []
        current_segment: dict = {"content": "", "tool_calls": []}

        async for event in agent.stream_chat_turn(
            message, history, session_id=session_id
        ):
            event_type = event.get("type", "unknown")

            if event_type == "token":
                current_segment["content"] += event["content"]
                yield {
                    "event": "token",
                    "data": json.dumps(
                        {"content": event["content"]}, ensure_ascii=False
                    ),
                }

            elif event_type == "new_response":
                segments.append(current_segment)
                current_segment = {"content": "", "tool_calls": []}
                yield {
                    "event": "new_response",
                    "data": json.dumps({}, ensure_ascii=False),
                }

            elif event_type == "tool_start":
                current_segment["tool_calls"].append(
                    {"tool": event["tool"], "input": event.get("input", "")}
                )
                yield {
                    "event": "tool_start",
                    "data": json.dumps(
                        {"tool": event["tool"], "input": event["input"]},
                        ensure_ascii=False,
                    ),
                }

            elif event_type == "tool_end":
                for tc in reversed(current_segment["tool_calls"]):
                    if tc["tool"] == event["tool"] and "output" not in tc:
                        tc["output"] = event["output"]
                        break
                yield {
                    "event": "tool_end",
                    "data": json.dumps(
                        {"tool": event["tool"], "output": event["output"]},
                        ensure_ascii=False,
                    ),
                }

            elif event_type == "done":
                segments.append(current_segment)
                all_content = "".join(seg["content"] for seg in segments)
                recall_mode = event.get("recall_mode", "full")
                # 仅展示召回的旧记忆；本轮 Judge 新增/更新的条目不标为 Memories used
                injected_ids = event.get("injected_entry_ids") or []
                recall_ids = _filter_recall_memory_ids(injected_ids, memory_result)
                turn_refs = _build_memory_refs_from_ids(uid, recall_ids)

                # 与后续 title / memory 并行生成追问建议
                suggest_task = asyncio.create_task(
                    asyncio.to_thread(
                        _generate_suggested_questions, message, all_content
                    )
                )

                save_t0 = time.perf_counter()
                save_message(uid, session_id, "user", message)
                for i, seg in enumerate(segments):
                    tc = seg["tool_calls"] if seg["tool_calls"] else None
                    # 引用卡片挂在最后一段助手消息上
                    seg_refs = turn_refs if i == len(segments) - 1 else None
                    save_message(
                        uid,
                        session_id,
                        "assistant",
                        seg["content"],
                        tool_calls=tc,
                        memory_refs=seg_refs if seg_refs else None,
                    )
                logger.info(
                    "chat_persist uid=%s session=%s segments=%d "
                    "injected_refs=%d elapsed=%.3fs",
                    uid,
                    session_id,
                    len(segments),
                    len(turn_refs),
                    time.perf_counter() - save_t0,
                )

                if turn_refs:
                    yield {
                        "event": "memory_ref",
                        "data": json.dumps({"refs": turn_refs}, ensure_ascii=False),
                    }

                yield {
                    "event": "done",
                    "data": json.dumps(
                        {
                            "content": event["content"],
                            "session_id": session_id,
                            "recall_mode": recall_mode,
                        },
                        ensure_ascii=False,
                    ),
                }

                canvas_match = re.search(
                    rf"<{CANVAS_TAG}>(.*?)</{CANVAS_TAG}>",
                    all_content,
                    re.DOTALL,
                )
                if canvas_match:
                    yield {
                        "event": "canvas",
                        "data": json.dumps(
                            {"html": canvas_match.group(1).strip()},
                            ensure_ascii=False,
                        ),
                    }

                if is_first_message:
                    title_t0 = time.perf_counter()
                    title = await asyncio.to_thread(_generate_title, uid, session_id)
                    logger.info(
                        "chat_title uid=%s session=%s title=%r elapsed=%.3fs",
                        uid,
                        session_id,
                        title,
                        time.perf_counter() - title_t0,
                    )
                    if title:
                        yield {
                            "event": "title",
                            "data": json.dumps(
                                {"session_id": session_id, "title": title},
                                ensure_ascii=False,
                            ),
                        }

                # 下发追问建议（失败则静默跳过）
                try:
                    suggest_t0 = time.perf_counter()
                    questions = await suggest_task
                    logger.info(
                        "chat_suggest uid=%s session=%s count=%d elapsed=%.3fs",
                        uid,
                        session_id,
                        len(questions),
                        time.perf_counter() - suggest_t0,
                    )
                    if questions:
                        yield {
                            "event": "suggested_questions",
                            "data": json.dumps(
                                {"questions": questions}, ensure_ascii=False
                            ),
                        }
                except Exception:
                    traceback.print_exc()

                logger.info(
                    "chat_complete uid=%s session=%s total=%.3fs",
                    uid,
                    session_id,
                    time.perf_counter() - turn_t0,
                )

            elif event_type == "error":
                memory_task.cancel()
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"error": event.get("error", "Unknown error")},
                        ensure_ascii=False,
                    ),
                }

    except Exception as e:
        traceback.print_exc()
        yield {
            "event": "error",
            "data": json.dumps({"error": str(e)}, ensure_ascii=False),
        }


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: UserRecord = Depends(get_current_user),
):
    """
    SSE 流式聊天接口。

    参数:
        request (ChatRequest): 消息与会话 ID

    返回:
        EventSourceResponse: SSE 事件流
    """
    if request.stream:
        return EventSourceResponse(
            event_generator(user.uid, request.message, request.session_id)
        )

    history = load_history_for_agent(user.uid, request.session_id)
    memory_result = await _judge_and_apply_memory(
        user.uid, request.message, history, request.session_id
    )

    agent = Agent(uid=user.uid)
    full = ""
    recall_mode = "full"
    injected_ids: list[str] = []
    async for event in agent.stream_chat_turn(
        request.message, history, session_id=request.session_id
    ):
        if event.get("type") == "token":
            full += event.get("content", "")
        elif event.get("type") == "done":
            full = event.get("content", full)
            recall_mode = event.get("recall_mode", "full")
            injected_ids = event.get("injected_entry_ids") or []
    recall_ids = _filter_recall_memory_ids(injected_ids, memory_result)
    save_message(user.uid, request.session_id, "user", request.message)
    refs = _build_memory_refs_from_ids(user.uid, recall_ids)
    save_message(
        user.uid,
        request.session_id,
        "assistant",
        full,
        memory_refs=refs if refs else None,
    )
    return {"reply": full, "recall_mode": recall_mode}
