"""
Agent 工具执行时的用户上下文，供 update_user / write_file 等按用户隔离写入记忆。
"""

from __future__ import annotations

from contextvars import ContextVar

from src.memory_schema import MemorySourceContext

_current_uid: ContextVar[str | None] = ContextVar("tool_context_uid", default=None)
_current_session_id: ContextVar[str | None] = ContextVar(
    "tool_context_session_id", default=None
)
_current_user_message: ContextVar[str | None] = ContextVar(
    "tool_context_user_message", default=None
)


def set_tool_uid(uid: str | None) -> None:
    """
    设置当前工具执行所属用户 ID。

    参数:
        uid (str | None): 用户 ID；None 表示清除上下文

    返回:
        None
    """
    _current_uid.set(uid)


def set_tool_session_id(session_id: str | None) -> None:
    """
    设置当前工具执行所属的聊天会话 ID。

    参数:
        session_id (str | None): 会话 ID

    返回:
        None
    """
    _current_session_id.set(session_id)


def set_tool_user_message(message: str | None) -> None:
    """
    设置当前轮次的用户原话，供记忆来源追溯。

    参数:
        message (str | None): 用户消息正文

    返回:
        None
    """
    _current_user_message.set(message)


def set_tool_context(
    uid: str | None,
    *,
    session_id: str | None = None,
    user_message: str | None = None,
) -> None:
    """
    一次性设置工具执行所需的完整上下文。

    参数:
        uid (str | None): 用户 ID
        session_id (str | None): 会话 ID
        user_message (str | None): 用户原话

    返回:
        None
    """
    set_tool_uid(uid)
    set_tool_session_id(session_id)
    set_tool_user_message(user_message)


def clear_tool_context() -> None:
    """
    清除全部工具上下文。

    返回:
        None
    """
    set_tool_context(None, session_id=None, user_message=None)


def get_tool_uid() -> str | None:
    """
    获取当前工具执行所属用户 ID。

    返回:
        str | None: 用户 ID；未设置时返回 None
    """
    return _current_uid.get()


def get_tool_source_context() -> MemorySourceContext | None:
    """
    获取当前聊天上下文对应的记忆来源信息。

    返回:
        MemorySourceContext | None: 有会话或原话时返回来源，否则 None
    """
    session_id = _current_session_id.get()
    quote = (_current_user_message.get() or "").strip()
    if session_id or quote:
        return MemorySourceContext(
            source_type="tool",
            source_session_id=session_id,
            source_quote=quote or None,
        )
    return None


def require_tool_uid() -> str:
    """
    获取当前用户 ID，未登录上下文时抛出 ValueError。

    返回:
        str: 用户 ID

    Raises:
        ValueError: 未设置用户上下文
    """
    uid = get_tool_uid()
    if not uid:
        raise ValueError("未登录，无法执行需要用户身份的记忆操作")
    return uid
