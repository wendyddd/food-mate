"""
相关记忆召回：用大模型判断当前输入相关的记忆条目。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.config import DEFAULT_MODEL
from src.llm_client import LLMClient
from src.memory import list_entries
from src.memory_schema import MemoryEntry


@dataclass(frozen=True)
class RetrieveResult:
    """
    记忆相关性召回结果。

    参数:
        ok (bool): 是否成功（失败时应回退全量注入）
        entries (list[MemoryEntry]): 筛选出的相关条目（可为空）
    """

    ok: bool
    entries: list[MemoryEntry]


def _strip_json_fences(text: str) -> str:
    """
    去掉模型输出中的 JSON 代码围栏。

    参数:
        text (str): 原始输出

    返回:
        str: 纯 JSON 字符串
    """
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].lstrip("\n")
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].lstrip("\n")
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].rstrip()
    return cleaned.strip()


def _format_entries_for_prompt(entries: list[MemoryEntry]) -> str:
    """
    将记忆条目格式化为召回提示文本。

    参数:
        entries (list[MemoryEntry]): 记忆条目列表

    返回:
        str: 格式化文本
    """
    if not entries:
        return "(No memories yet)"
    lines = []
    for e in entries:
        lines.append(f"- id={e.id} | category={e.category} | content={e.content}")
    return "\n".join(lines)


def _format_recent_history(history: list[dict], max_turns: int = 4) -> str:
    """
    将近期对话格式化为短文本。

    参数:
        history (list[dict]): user/assistant 历史
        max_turns (int): 最多保留的轮数

    返回:
        str: 格式化对话
    """
    if not history:
        return "(No history)"
    tail = history[-(max_turns * 2) :]
    lines = []
    for msg in tail:
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = (msg.get("content") or "").strip()[:300]
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(No history)"


def _parse_relevant_ids(raw: str) -> list[str] | None:
    """
    解析模型输出的相关记忆 ID 列表。

    参数:
        raw (str): 模型原始输出

    返回:
        list[str] | None: 解析成功返回 ID 列表（可为空）；JSON 无效返回 None
    """
    cleaned = _strip_json_fences(raw)
    data = None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None
    ids_raw = data.get("relevant_ids", [])
    if not isinstance(ids_raw, list):
        return None

    result: list[str] = []
    for item in ids_raw:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def retrieve_relevant_memories(
    uid: str,
    user_message: str,
    history: list[dict],
    *,
    model: str = DEFAULT_MODEL,
) -> RetrieveResult:
    """
    根据当前用户输入，用大模型筛选相关长期记忆。

    参数:
        uid (str): 用户 ID
        user_message (str): 当前用户消息
        history (list[dict]): 不含 system 的近期历史
        model (str): 使用的模型名称

    返回:
        RetrieveResult: ok=True 时 entries 为筛选结果（可为空）；ok=False 表示应回退全量
    """
    entries = list_entries(uid)
    if not entries:
        return RetrieveResult(ok=True, entries=[])

    by_id = {e.id: e for e in entries}
    llm = LLMClient(default_model=model)
    system_prompt = (
        "You are the FoodMate memory retriever for a home cooking assistant. "
        "Given the user's latest message and brief conversation context, "
        "select which long-term memory entries are relevant to answering this turn. "
        "Include a memory if it constrains or personalizes the reply "
        "(allergies, taste, household, equipment, budget, etc.). "
        "Exclude memories that are clearly unrelated to the current question. "
        "It is valid to return an empty list when nothing is relevant. "
        "Only use IDs from the provided list; do not invent IDs. "
        'Output valid JSON only, format: {"relevant_ids": ["mem_xxx", "mem_yyy"]}. '
        "No explanation."
    )
    user_prompt = f"""
Available memory entries:
{_format_entries_for_prompt(entries)}

Recent conversation:
{_format_recent_history(history)}

Latest user message:
{user_message.strip()}

Select relevant memory IDs. Output JSON.
""".strip()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = llm.chat(messages=messages)
        parsed_ids = _parse_relevant_ids(response.content or "")
    except Exception:
        return RetrieveResult(ok=False, entries=[])

    if parsed_ids is None:
        return RetrieveResult(ok=False, entries=[])

    # 校验存在、去重保序
    selected: list[MemoryEntry] = []
    seen: set[str] = set()
    for eid in parsed_ids:
        if eid in seen:
            continue
        seen.add(eid)
        entry = by_id.get(eid)
        if entry is not None:
            selected.append(entry)

    return RetrieveResult(ok=True, entries=selected)
