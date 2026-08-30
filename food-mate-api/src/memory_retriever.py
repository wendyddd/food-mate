"""
Relevant memory recall: use an LLM to pick memory entries related to the current input.
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
    Result of relevance-based memory recall.

    Attributes:
        ok (bool): Whether recall succeeded (on failure, fall back to injecting all)
        entries (list[MemoryEntry]): Filtered relevant entries (may be empty)
    """

    ok: bool
    entries: list[MemoryEntry]


def _strip_json_fences(text: str) -> str:
    """
    Strip JSON code fences from model output.

    Args:
        text (str): Raw output

    Returns:
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


def _format_entries_for_prompt(entries: list[MemoryEntry]) -> str:
    """
    Format memory entries as recall-prompt text.

    Args:
        entries (list[MemoryEntry]): Memory entry list

    Returns:
        str: Formatted text
    """
    if not entries:
        return "(No memories yet)"
    lines = []
    for e in entries:
        lines.append(f"- id={e.id} | category={e.category} | content={e.content}")
    return "\n".join(lines)


def _format_recent_history(history: list[dict], max_turns: int = 4) -> str:
    """
    Format recent conversation as short text.

    Args:
        history (list[dict]): user/assistant history
        max_turns (int): Max turns to keep

    Returns:
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


def _parse_relevant_ids(raw: str) -> list[str] | None:
    """
    Parse relevant memory IDs from model output.

    Args:
        raw (str): Raw model output

    Returns:
        list[str] | None: ID list on success (may be empty); None if JSON is invalid
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
    Use an LLM to filter long-term memories relevant to the current user input.

    Args:
        uid (str): User ID
        user_message (str): Current user message
        history (list[dict]): Recent history without system messages
        model (str): Model name to use

    Returns:
        RetrieveResult: When ok=True, entries is the filtered set (may be empty);
            ok=False means fall back to injecting all memories
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

    # Validate existence, dedupe, keep order
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
