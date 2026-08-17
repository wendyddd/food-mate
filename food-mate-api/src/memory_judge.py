"""
Per-turn memory judge — decides whether to write structured memory from user messages.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.config import DEFAULT_MODEL
from src.llm_client import LLMClient
from src.memory import apply_operations, list_entries
from src.memory_schema import (
    ApplyResult,
    MEMORY_CATEGORIES,
    MemoryOperation,
    MemorySourceContext,
    categories_prompt_block,
    normalize_category,
)


@dataclass(frozen=True)
class JudgeResult:
    """
    Single-turn memory judgment result.

    参数:
        changed (bool): Whether memory was written
        apply_result (ApplyResult): Apply operation details
    """

    changed: bool
    apply_result: ApplyResult


def _strip_json_fences(text: str) -> str:
    """
    Remove JSON code fences from model output if present.

    参数:
        text (str): Raw output

    返回:
        str: Plain JSON string
    """
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].lstrip("\n")
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].lstrip("\n")
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].rstrip()
    return cleaned.strip()


def _format_entries_for_prompt(entries: list) -> str:
    """
    Format current memory entries for the judge prompt.

    参数:
        entries (list): MemoryEntry list

    返回:
        str: Formatted text
    """
    if not entries:
        return "(No memories yet)"
    lines = []
    for e in entries:
        # 附带时间戳，便于冲突时判断新旧
        lines.append(
            f"- id={e.id} | category={e.category} | updated_at={e.updated_at:.0f} | content={e.content}"
        )
    return "\n".join(lines)


def _format_recent_history(history: list[dict], max_turns: int = 4) -> str:
    """
    Format recent conversation turns as short text.

    参数:
        history (list[dict]): user/assistant history
        max_turns (int): Max turns to include (user+assistant = one turn)

    返回:
        str: Formatted conversation
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


def _parse_operations_json(raw: str) -> list[MemoryOperation]:
    """
    Parse JSON operation list from LLM output.

    参数:
        raw (str): LLM output text

    返回:
        list[MemoryOperation]: Operation list
    """
    cleaned = _strip_json_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

    ops_raw = data.get("operations", [])
    if not isinstance(ops_raw, list):
        return []

    operations: list[MemoryOperation] = []
    for item in ops_raw:
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        if action not in ("add", "update", "delete"):
            continue
        op = MemoryOperation.from_dict(item)
        if op.category:
            op = MemoryOperation(
                action=op.action,
                category=normalize_category(op.category),
                content=op.content,
                entry_id=op.entry_id,
            )
        operations.append(op)
    return operations


def judge_memory_from_turn(
    user_message: str,
    history: list[dict],
    uid: str,
    *,
    session_id: str | None = None,
    model: str = DEFAULT_MODEL,
) -> JudgeResult:
    """
    Decide whether to update structured memory from this user message and apply changes.

    参数:
        user_message (str): Current user message
        history (list[dict]): History without system messages
        uid (str): User ID
        session_id (str | None): Current session ID for source tracing
        model (str): Model to use

    返回:
        JudgeResult: Judgment and apply result
    """
    entries = list_entries(uid)
    current_entries_text = _format_entries_for_prompt(entries)
    recent_history = _format_recent_history(history)

    categories_str = ", ".join(MEMORY_CATEGORIES)
    category_guide = categories_prompt_block()

    llm = LLMClient(default_model=model)
    system_prompt = (
        "You are the FoodMate memory judge for a home cooking assistant. "
        "Based on the user's latest message (and brief context), decide whether to update their long-term cooking profile. "
        "Only act when the user clearly expresses a stable, cooking-relevant preference or constraint. "
        "For small talk, one-off recipe questions without personal preferences, or non-cooking topics, "
        "operations must be an empty array. "
        "Classification rules: "
        "hard constraints/allergies/religious diets/health goals → Health & Dietary Restrictions; "
        "flavor likes/dislikes/cuisines/cooking skill/habits → Taste & Habits; "
        "family members/portions/time budget/meal scenarios → Household & Context; "
        "equipment/pantry staples/budget → Kitchen & Budget; "
        "Other only when none of the above fits and the fact is still long-term useful. "
        "Prefer the first four categories over Other. "
        "Merge & conflict rules (must follow): "
        "1) ONE keyword fact = ONE memory entry / one operation. "
        "If the user states multiple distinct facts, emit multiple add/update operations — "
        "NEVER join different facts with '; ' into one content string. "
        "2) If a new fact is a near-paraphrase of the SAME fact "
        "(e.g. '喜欢吃辣' vs '爱吃辣', or 'likes spicy' vs 'prefers spicy food'), "
        "use update on that entry_id with a short keyword — do NOT add a duplicate. "
        "Different facts in the same category MUST be SEPARATE entries. "
        "Examples that must stay independent: "
        "'喜欢吃辣' vs '喜欢吃酸的' → two add operations (never update one into the other); "
        "'likes spicy' vs 'likes sour'; lactose intolerant vs peanut allergy. "
        "3) If a new fact conflicts with an existing entry (e.g. liked spicy vs avoids spicy), "
        "use update on that entry_id with the newer information; "
        "or delete the outdated entry and add the new one. Prefer the latest user statement. "
        "4) Only use add when no similar or conflicting entry exists for that same fact. "
        "Write memory content in the same language as the user's message. "
        "Content style (must follow): each content is ONE short keyword phrase "
        "(e.g. 'lactose intolerant' or '乳糖不耐受'), under about 8 words / 12 Chinese characters. "
        "Do NOT write full sentences, explanations, parenthetical elaborations, or multi-fact strings. "
        "Output valid JSON only, format: "
        '{"operations": [{"action":"add","category":"Taste & Habits","content":"..."}, '
        '{"action":"update","entry_id":"mem_xxx","content":"..."}, '
        '{"action":"delete","entry_id":"mem_xxx"}]} '
        f"category must be one of: {categories_str}. "
        f"Category meanings:\n{category_guide}\n"
        "update/delete require entry_id; add requires category and content. "
        "Output JSON only, no explanation."
    )

    user_prompt = f"""
Current memory entries:
{current_entries_text}

Recent conversation:
{recent_history}

Latest user message:
{user_message.strip()}

Decide whether memory should be updated. Output JSON.
""".strip()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = llm.chat(messages=messages)
        operations = _parse_operations_json(response.content or "")
    except Exception:
        store_entries = list_entries(uid)
        return JudgeResult(
            changed=False,
            apply_result=ApplyResult(changed=False, entries=store_entries),
        )

    apply_result = apply_operations(
        uid,
        operations,
        source=MemorySourceContext(
            source_type="judge",
            source_session_id=session_id,
            source_quote=user_message.strip(),
        )
        if session_id
        else MemorySourceContext(
            source_type="judge",
            source_quote=user_message.strip(),
        ),
    )
    return JudgeResult(changed=apply_result.changed, apply_result=apply_result)
