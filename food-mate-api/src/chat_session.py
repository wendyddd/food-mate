"""
Web 聊天会话管理，基于 JSON 文件持久化对话历史。
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any

from src.config import MEMORY_DIR, PROJECT_ROOT
from src.memory import ensure_memory_dirs, get_user_sessions_dir

# CLI / 遗留全局会话目录
SESSIONS_DIR = MEMORY_DIR / "sessions"
_LEGACY_SESSIONS_DIR = PROJECT_ROOT / "data" / "chat_sessions"

_ROLE_LABELS = {"user": "User", "assistant": "Assistant"}


def _sessions_dir(uid: str) -> Path:
    """
    解析指定用户的会话存储目录。

    参数:
        uid (str): 用户 ID

    返回:
        Path: sessions 目录路径
    """
    ensure_memory_dirs(uid)
    return get_user_sessions_dir(uid)


def _migrate_legacy_sessions(uid: str) -> None:
    """
    将旧目录 data/chat_sessions 中的会话 JSON 迁移到用户 sessions 目录。

    参数:
        uid (str): 目标用户 ID

    返回:
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
    确保用户聊天会话目录存在，并迁移旧目录中的会话文件。

    参数:
        uid (str): 用户 ID

    返回:
        None
    """
    _sessions_dir(uid).mkdir(parents=True, exist_ok=True)
    _migrate_legacy_sessions(uid)


def _session_path(uid: str, session_id: str) -> Path:
    """
    根据 session_id 解析安全的 JSON 文件路径。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        Path: 会话 JSON 文件路径
    """
    safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return _sessions_dir(uid) / f"{safe_id}.json"


def _read_file(uid: str, session_id: str) -> dict[str, Any]:
    """
    读取会话 JSON 并规范化为 v2 结构。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        dict: 会话数据；不存在时返回空 dict
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
    写入会话 JSON 文件。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID
        data (dict): 会话完整数据

    返回:
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
    列出指定用户的所有 Web 聊天会话元信息。

    参数:
        uid (str): 用户 ID

    返回:
        list[dict]: 含 id、title、updated_at 的会话列表
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
    为指定用户创建新的空聊天会话。

    参数:
        uid (str): 用户 ID

    返回:
        dict: 含 id、title 的会话元信息
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
    重命名会话。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID
        title (str): 新标题

    返回:
        None

    Raises:
        FileNotFoundError: 会话不存在
    """
    data = _read_file(uid, session_id)
    if not data:
        raise FileNotFoundError(f"Session {session_id} not found")
    data["title"] = title
    _write_file(uid, session_id, data)


def update_title(uid: str, session_id: str, title: str) -> None:
    """
    更新会话标题（rename_session 别名）。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID
        title (str): 新标题

    返回:
        None
    """
    rename_session(uid, session_id, title)


def _session_file_candidates(uid: str, session_id: str) -> list[Path]:
    """
    列出指定 session 可能存在的所有 JSON 文件路径（含遗留目录）。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        list[Path]: 候选路径列表（按优先级去重）
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
    删除会话 JSON 文件（用户目录及遗留全局目录中的副本）。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        bool: 是否至少删除一个文件
    """
    deleted = False
    for path in _session_file_candidates(uid, session_id):
        if path.exists():
            path.unlink()
            deleted = True
    return deleted


def load_history(uid: str, session_id: str) -> list[dict[str, Any]]:
    """
    加载会话对话历史（不含 system prompt）。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        list[dict]: 消息列表
    """
    data = _read_file(uid, session_id)
    if not data:
        return []
    return data.get("messages", [])


def load_history_for_agent(uid: str, session_id: str) -> list[dict[str, Any]]:
    """
    加载供 Agent 使用的历史，合并连续 assistant 消息。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        list[dict]: 合并后的 user/assistant 消息列表
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
    向会话追加一条消息。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID
        role (str): 角色（user / assistant）
        content (str): 消息正文
        tool_calls (list | None): 可选工具调用记录
        memory_refs (list | None): 可选记忆引用列表

    返回:
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
    获取会话完整数据（含 title 与 messages）。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        dict: 会话数据
    """
    data = _read_file(uid, session_id)
    if not data:
        return {"title": "", "messages": []}
    return data


def get_message_count(uid: str, session_id: str) -> int:
    """
    获取会话消息条数。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        int: 消息数量
    """
    data = _read_file(uid, session_id)
    if not data:
        return 0
    return len(data.get("messages", []))


def format_session_as_log(uid: str, session_id: str) -> str:
    """
    将 Web 聊天会话格式化为可供记忆提取器使用的文本日志。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        str: 格式化后的会话文本；会话不存在或无消息时返回空字符串
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
    获取指定 Web 聊天会话的格式化文本内容。

    参数:
        uid (str): 用户 ID
        session_id (str): 会话 ID

    返回:
        str: 会话文本内容
    """
    return format_session_as_log(uid, session_id)


def get_latest_session_content(uid: str) -> str:
    """
    获取指定用户最近一次 Web 聊天会话的格式化文本内容。

    参数:
        uid (str): 用户 ID

    返回:
        str: 最近会话的全文内容；若没有任何会话则返回空字符串
    """
    sessions = list_sessions(uid)
    if not sessions:
        return ""
    return format_session_as_log(uid, sessions[0]["id"])
