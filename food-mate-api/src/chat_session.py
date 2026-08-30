"""
Web chat session management, persisting conversation history as JSON files.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any

from src.config import MEMORY_DIR, PROJECT_ROOT
from src.memory import ensure_memory_dirs, get_user_sessions_dir

# CLI / legacy global session directory
SESSIONS_DIR = MEMORY_DIR / "sessions"
_LEGACY_SESSIONS_DIR = PROJECT_ROOT / "data" / "chat_sessions"

_ROLE_LABELS = {"user": "User", "assistant": "Assistant"}


def _sessions_dir(uid: str) -> Path:
    """
    Resolve the session storage directory for a user.

    Args:
        uid (str): User ID

    Returns:
        Path: sessions directory path
    """
    ensure_memory_dirs(uid)
    return get_user_sessions_dir(uid)


def _migrate_legacy_sessions(uid: str) -> None:
    """
    Migrate session JSON files from the legacy data/chat_sessions directory
    into the user's sessions directory.

    Args:
        uid (str): Target user ID

    Returns:
        None
    """
    sessions_dir = _sessions_dir(uid)
    if not _LEGACY_SESSIONS_DIR.exists():
        return
    for legacy_file in _LEGACY_SESSIONS_DIR.glob("*.json"):
        target = sessions_dir / legacy_file.name
        if target.exists():
            continue
        target.write_bytes(legacy_file.read_bytes())


def _ensure_dir(uid: str) -> None:
    """
    Ensure the user's chat session directory exists and migrate legacy session files.

    Args:
        uid (str): User ID

    Returns:
        None
    """
    _sessions_dir(uid).mkdir(parents=True, exist_ok=True)
    _migrate_legacy_sessions(uid)


def _session_path(uid: str, session_id: str) -> Path:
    """
    Resolve a safe JSON file path from session_id.

    Args:
        uid (str): User ID
        session_id (str): Session ID

    Returns:
        Path: Session JSON file path
    """
    safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return _sessions_dir(uid) / f"{safe_id}.json"


def _read_file(uid: str, session_id: str) -> dict[str, Any]:
    """
    Read session JSON and normalize it to the v2 structure.

    Args:
        uid (str): User ID
        session_id (str): Session ID

    Returns:
        dict: Session data; empty dict if missing
    """
    path = _session_path(uid, session_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            now = time.time()
            return {
                "title": session_id,
                "created_at": path.stat().st_ctime,
                "updated_at": now,
                "messages": data,
            }
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def _write_file(uid: str, session_id: str, data: dict[str, Any]) -> None:
    """
    Write the session JSON file.

    Args:
        uid (str): User ID
        session_id (str): Session ID
        data (dict): Full session data

    Returns:
        None
    """
    _ensure_dir(uid)
    data["updated_at"] = time.time()
    _session_path(uid, session_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_sessions(uid: str) -> list[dict[str, Any]]:
    """
    List metadata for all web chat sessions of a user.

    Args:
        uid (str): User ID

    Returns:
        list[dict]: Session list with id, title, and updated_at
    """
    sessions_dir = _sessions_dir(uid)
    _ensure_dir(uid)
    sessions: list[dict[str, Any]] = []
    for f in sorted(
        sessions_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                title = raw.get("title", f.stem)
                updated_at = raw.get("updated_at", f.stat().st_mtime)
            else:
                title = f.stem
                updated_at = f.stat().st_mtime
        except Exception:
            title = f.stem
            updated_at = f.stat().st_mtime
        sessions.append({"id": f.stem, "title": title, "updated_at": updated_at})
    return sessions


def create_session(uid: str) -> dict[str, Any]:
    """
    Create a new empty chat session for a user.

    Args:
        uid (str): User ID

    Returns:
        dict: Session metadata with id and title
    """
    session_id = f"session-{uuid.uuid4().hex[:12]}"
    now = time.time()
    data: dict[str, Any] = {
        "title": "New Chat",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _write_file(uid, session_id, data)
    return {"id": session_id, "title": data["title"], "updated_at": now}


def rename_session(uid: str, session_id: str, title: str) -> None:
    """
    Rename a session.

    Args:
        uid (str): User ID
        session_id (str): Session ID
        title (str): New title

    Returns:
        None

    Raises:
        FileNotFoundError: Session does not exist
    """
    data = _read_file(uid, session_id)
    if not data:
        raise FileNotFoundError(f"Session {session_id} not found")
    data["title"] = title
    _write_file(uid, session_id, data)


def update_title(uid: str, session_id: str, title: str) -> None:
    """
    Update the session title (alias of rename_session).

    Args:
        uid (str): User ID
        session_id (str): Session ID
        title (str): New title

    Returns:
        None
    """
    rename_session(uid, session_id, title)


def _session_file_candidates(uid: str, session_id: str) -> list[Path]:
    """
    List all possible JSON paths for a session (including legacy directories).

    Args:
        uid (str): User ID
        session_id (str): Session ID

    Returns:
        list[Path]: Candidate paths (deduped by priority)
    """
    safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
    filename = f"{safe_id}.json"
    seen: set[Path] = set()
    candidates: list[Path] = []

    def _add(path: Path) -> None:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(path)

    _add(_session_path(uid, session_id))
    _add(_LEGACY_SESSIONS_DIR / filename)
    _add(SESSIONS_DIR / filename)
    return candidates


def delete_session(uid: str, session_id: str) -> bool:
    """
    Delete session JSON files (user directory and legacy global copies).

    Args:
        uid (str): User ID
        session_id (str): Session ID

    Returns:
        bool: Whether at least one file was deleted
    """
    deleted = False
    for path in _session_file_candidates(uid, session_id):
        if path.exists():
            path.unlink()
            deleted = True
    return deleted


def load_history(uid: str, session_id: str) -> list[dict[str, Any]]:
    """
    Load session conversation history (without the system prompt).

    Args:
        uid (str): User ID
        session_id (str): Session ID

    Returns:
        list[dict]: Message list
    """
    data = _read_file(uid, session_id)
    if not data:
        return []
    return data.get("messages", [])


def load_history_for_agent(uid: str, session_id: str) -> list[dict[str, Any]]:
    """
    Load history for the Agent, merging consecutive assistant messages.

    Args:
        uid (str): User ID
        session_id (str): Session ID

    Returns:
        list[dict]: Merged user/assistant message list
    """
    messages = load_history(uid, session_id)
    merged: list[dict[str, Any]] = []
    for msg in messages:
        if merged and merged[-1]["role"] == "assistant" and msg["role"] == "assistant":
            merged[-1]["content"] += "\n" + msg["content"]
        else:
            merged.append({"role": msg["role"], "content": msg["content"]})
    return merged


def save_message(
    uid: str,
    session_id: str,
    role: str,
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
    memory_refs: list[dict[str, Any]] | None = None,
) -> None:
    """
    Append one message to the session.

    Args:
        uid (str): User ID
        session_id (str): Session ID
        role (str): Role (user / assistant)
        content (str): Message body
        tool_calls (list | None): Optional tool-call records
        memory_refs (list | None): Optional memory reference list

    Returns:
        None
    """
    data = _read_file(uid, session_id)
    if not data:
        now = time.time()
        data = {
            "title": "New Chat",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
    msg: dict[str, Any] = {"role": role, "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if memory_refs:
        msg["memory_refs"] = memory_refs
    data["messages"].append(msg)
    _write_file(uid, session_id, data)


def get_raw_messages(uid: str, session_id: str) -> dict[str, Any]:
    """
    Get full session data (title and messages).

    Args:
        uid (str): User ID
        session_id (str): Session ID

    Returns:
        dict: Session data
    """
    data = _read_file(uid, session_id)
    if not data:
        return {"title": "", "messages": []}
    return data


def get_message_count(uid: str, session_id: str) -> int:
    """
    Get the number of messages in the session.

    Args:
        uid (str): User ID
        session_id (str): Session ID

    Returns:
        int: Message count
    """
    data = _read_file(uid, session_id)
    if not data:
        return 0
    return len(data.get("messages", []))


def format_session_as_log(uid: str, session_id: str) -> str:
    """
    Format a web chat session as a text log for the memory extractor.

    Args:
        uid (str): User ID
        session_id (str): Session ID

    Returns:
        str: Formatted session text; empty string if missing or no messages
    """
    data = _read_file(uid, session_id)
    if not data:
        return ""

    title = data.get("title", session_id)
    messages = data.get("messages", [])
    if not messages:
        return ""

    lines = [f"# 会话日志 {title}\n"]
    for msg in messages:
        role = _ROLE_LABELS.get(msg.get("role", ""), msg.get("role", "未知"))
        content = (msg.get("content") or "").strip()
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            tool_parts = []
            for tc in tool_calls:
                tool_name = tc.get("tool", "unknown")
                tool_output = tc.get("output", "")
                tool_parts.append(f"[{tool_name}] {tool_output}")
            tool_text = "\n".join(tool_parts)
            content = f"{content}\n\n{tool_text}".strip() if content else tool_text
        if not content:
            continue
        lines.append(f"## {role}\n\n{content}\n")
    return "\n".join(lines).strip()


def get_session_content(uid: str, session_id: str) -> str:
    """
    Get formatted text content of a web chat session.

    Args:
        uid (str): User ID
        session_id (str): Session ID

    Returns:
        str: Session text content
    """
    return format_session_as_log(uid, session_id)


def get_latest_session_content(uid: str) -> str:
    """
    Get formatted text of the user's most recent web chat session.

    Args:
        uid (str): User ID

    Returns:
        str: Full text of the latest session; empty string if none exist
    """
    sessions = list_sessions(uid)
    if not sessions:
        return ""
    return format_session_as_log(uid, sessions[0]["id"])
