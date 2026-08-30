"""
POST /api/chat — SSE streaming chat endpoint.
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
    """Chat request body."""

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
    Run this turn's memory judgment in the background and persist results.

    Args:
        uid (str): user ID
        message (str): user message
        history (list): conversation history
        session_id (str): current session ID

    Returns:
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
    Drop entries added or updated by this turn's Judge from injected IDs, keeping only recalled older memories.

    Args:
        injected_ids (list[str]): all memory IDs injected this turn
        memory_result (dict | None): Judge result, including added_ids / updated_ids

    Returns:
        list[str]: memory IDs suitable for the "Memories used" display
    """
    if not injected_ids:
        return []
    result = memory_result or {}
    exclude = set(result.get("added_ids") or []) | set(result.get("updated_ids") or [])
    return [mid for mid in injected_ids if mid not in exclude]


def _build_memory_refs_from_ids(uid: str, entry_ids: list[str]) -> list[dict[str, str]]:
    """
    Build frontend display refs from a list of memory IDs.

    Args:
        uid (str): user ID
        entry_ids (list[str]): memory IDs injected or referenced this turn

    Returns:
        list[dict]: list of reference entries
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
    Generate a session title from the first turn (sync; for to_thread).

    Args:
        uid (str): user ID
        session_id (str): session ID

    Returns:
        str | None: generated title, or None on failure
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
    Parse follow-up questions from model output (prefer a JSON array, else split by line).

    Args:
        raw (str): raw model output

    Returns:
        list[str]: up to 3 non-empty follow-up questions
    """
    text = (raw or "").strip()
    if not text:
        return []

    # Try to extract a JSON array
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

    # Split by line and strip numbering prefixes
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
    Generate about 3 short follow-up questions from this turn (sync; for to_thread).

    Args:
        user_message (str): user message this turn
        assistant_content (str): full assistant reply this turn

    Returns:
        list[str]: follow-up questions, or an empty list on failure
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
    Stream SSE events from the Agent and persist the session.

    Args:
        uid (str): user ID
        message (str): user message
        session_id (str): session ID

    Yields:
        dict: SSE event {event, data}
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

        # Finish memory judgment first; if anything changed, send a Toast before generating the reply
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
                # Show only recalled older memories; entries added/updated by this turn's Judge are not marked as Memories used
                injected_ids = event.get("injected_entry_ids") or []
                recall_ids = _filter_recall_memory_ids(injected_ids, memory_result)
                turn_refs = _build_memory_refs_from_ids(uid, recall_ids)

                # Generate follow-up suggestions in parallel with title / memory work
                suggest_task = asyncio.create_task(
                    asyncio.to_thread(
                        _generate_suggested_questions, message, all_content
                    )
                )

                save_t0 = time.perf_counter()
                save_message(uid, session_id, "user", message)
                for i, seg in enumerate(segments):
                    tc = seg["tool_calls"] if seg["tool_calls"] else None
                    # Attach reference cards to the last assistant segment
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

                # Send follow-up suggestions (skip silently on failure)
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
    SSE streaming chat endpoint.

    Args:
        request (ChatRequest): message and session ID

    Returns:
        EventSourceResponse: SSE event stream
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
