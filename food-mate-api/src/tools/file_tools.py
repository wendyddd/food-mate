"""
File read/write tools — read_file, write_file, and update_user for local text files.
"""

from pathlib import Path

from src.config import MEMORY_DIR
from src.memory import get_user_memory_dir
from src.memory_schema import (
    MEMORY_CATEGORIES,
    MemorySourceContext,
    categories_prompt_block,
)
from src.tool_context import get_tool_source_context, require_tool_uid
from src.tools.registry import registry

# Max chars when reading a file to avoid filling context
MAX_READ_CHARS = 20000

_CATEGORIES_DESC = ", ".join(MEMORY_CATEGORIES)
_CATEGORIES_GUIDE = categories_prompt_block()


def _resolve_user_memory_path(path: str, uid: str) -> Path | None:
    """
    解析并校验路径，限定在当前登录用户的 memory/users/{uid}/ 目录下。

    若路径形如 memory/users/<任意段>/...，强制改写为当前 uid 目录，
    避免模型使用 default、current、{uid} 等占位符。

    参数:
        path (str): 目标文件路径
        uid (str): 当前登录用户 ID

    返回:
        Path | None: 合法绝对路径，非法时返回 None
    """
    memory_root = MEMORY_DIR.resolve()
    user_root = get_user_memory_dir(uid).resolve()

    raw_path = (path or "").strip()
    if not raw_path:
        return None

    p = Path(raw_path).expanduser()
    if p.is_absolute():
        file_path = p.resolve()
    else:
        norm = raw_path.replace("\\", "/").lstrip("./")
        if norm.startswith("memory/"):
            file_path = (memory_root / norm[len("memory/") :]).resolve()
        elif norm.startswith("users/"):
            file_path = (memory_root / norm).resolve()
        else:
            file_path = (user_root / norm).resolve()

    try:
        rel = file_path.relative_to(memory_root)
        if len(rel.parts) >= 2 and rel.parts[0] == "users":
            suffix_parts = rel.parts[2:]
            file_path = user_root.joinpath(*suffix_parts).resolve()
    except ValueError:
        if not str(file_path).startswith(str(user_root)):
            return None

    if not str(file_path).startswith(str(user_root)):
        return None
    return file_path


@registry.register(
    name="read_file",
    description=(
        "Read a text file under the current logged-in user's memory directory. "
        "The user's cooking profile is already in the system prompt — do not read user.md "
        "unless you have a specific reason. Never use paths like memory/users/default/."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "File path under the current user's memory directory "
                    "(e.g. user.md or sessions/notes.txt). "
                    "Must not use default, current, or placeholder user IDs."
                ),
            }
        },
        "required": ["path"],
    },
)
def read_file(path: str) -> str:
    """
    读取当前用户记忆目录下的文本文件。

    参数:
        path (str): 文件路径

    返回:
        str: 文件内容或错误信息
    """
    try:
        uid = require_tool_uid()
        file_path = _resolve_user_memory_path(path, uid)
        if file_path is None:
            return f"[read_file failed] Access denied: {path}"
    except ValueError as e:
        return f"[read_file failed] {e}"

    if not file_path.exists():
        return f"[read_file failed] File not found: {path}"
    if not file_path.is_file():
        return f"[read_file failed] Not a file: {path}"

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"[read_file failed] {path}: {e}"

    if len(content) > MAX_READ_CHARS:
        content = content[:MAX_READ_CHARS] + "\n...[truncated — content too long]"
    return content


@registry.register(
    name="write_file",
    description=(
        "Write text to a file under the current logged-in user's memory directory (overwrite). "
        "Prefer update_user for structured profile changes. "
        "Never use paths like memory/users/default/."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Target path under the current user's memory directory "
                    "(e.g. user.md). Must not use default or placeholder user IDs."
                ),
            },
            "content": {
                "type": "string",
                "description": "Text to write",
            },
        },
        "required": ["path", "content"],
    },
)
def write_file(path: str, content: str) -> str:
    """
    写入当前用户记忆目录下的文本文件。

    参数:
        path (str): 目标文件路径
        content (str): 要写入的文本

    返回:
        str: 成功或失败信息
    """
    try:
        uid = require_tool_uid()
        file_path = _resolve_user_memory_path(path, uid)
        if file_path is None:
            return f"[write_file failed] Access denied: {path}"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except ValueError as e:
        return f"[write_file failed] {e}"
    except Exception as e:
        return f"[write_file failed] {path}: {e}"
    return f"[write_file ok] Wrote {len(content)} characters to {path}"


@registry.register(
    name="update_user",
    description=(
        "Add or update a structured memory entry in the user's long-term cooking profile. "
        "Prefer updating an existing similar entry via entry_id only when it is the SAME fact. "
        "Do NOT add a new entry that restates preferences the user just said in this turn "
        "(the Memory Judge already records those). "
        "Each call stores ONE short keyword phrase; different facts need separate calls."
    ),
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": (
                    f"Memory category (one of: {_CATEGORIES_DESC}). "
                    f"Meanings:\n{_CATEGORIES_GUIDE}"
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "ONE short keyword phrase only "
                    "(e.g. 'lactose intolerant' or '乳糖不耐受'). "
                    "Do not join multiple facts; call again for each fact."
                ),
            },
            "entry_id": {
                "type": "string",
                "description": "Optional entry ID when updating existing memory",
            },
        },
        "required": ["category", "content"],
    },
)
def update_user(category: str, content: str, entry_id: str = "") -> str:
    """
    为当前用户新增或更新结构化记忆条目。

    参数:
        category (str): 记忆分类
        content (str): 记忆文本
        entry_id (str): 可选，更新已有条目时传入

    返回:
        str: 操作结果信息
    """
    try:
        uid = require_tool_uid()
        from src.memory import add_entry, update_entry

        # 对话中由 Agent 调用时记为 tool；无会话上下文时才回退为 manual
        source = get_tool_source_context() or MemorySourceContext(source_type="manual")

        if entry_id:
            entry = update_entry(uid, entry_id, content, source=source)
            return f"[update_user ok] Updated {entry.id}: {entry.content[:50]}"
        entry = add_entry(uid, category, content, source=source)
        return f"[update_user ok] Added {entry.id}: {entry.content[:50]}"
    except ValueError as e:
        return f"[update_user failed] {e}"
    except Exception as e:
        return f"[update_user failed] {e}"
