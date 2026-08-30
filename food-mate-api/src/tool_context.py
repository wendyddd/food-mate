"""
User context for Agent tool execution, so update_user / write_file isolate memory by user.
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
    Set the user ID for the current tool execution.

    Args:
        uid (str | None): User ID; None clears the context

    Returns:
        None
    """
    _current_uid.set(uid)


def set_tool_session_id(session_id: str | None) -> None:
    """
    Set the chat session ID for the current tool execution.

    Args:
        session_id (str | None): Session ID

    Returns:
        None
    """
    _current_session_id.set(session_id)


def set_tool_user_message(message: str | None) -> None:
    """
    Set the current-turn user quote for memory source tracing.

    Args:
        message (str | None): User message body

    Returns:
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
    Set the full tool-execution context in one call.

    Args:
        uid (str | None): User ID
        session_id (str | None): Session ID
        user_message (str | None): User quote

    Returns:
        None
    """
    set_tool_uid(uid)
    set_tool_session_id(session_id)
    set_tool_user_message(user_message)


def clear_tool_context() -> None:
    """
    Clear all tool context.

    Returns:
        None
    """
    set_tool_context(None, session_id=None, user_message=None)


def get_tool_uid() -> str | None:
    """
    Get the user ID for the current tool execution.

    Returns:
        str | None: User ID; None if unset
    """
    return _current_uid.get()


def get_tool_source_context() -> MemorySourceContext | None:
    """
    Get memory source info for the current chat context.

    Returns:
        MemorySourceContext | None: Source if a session or quote exists, otherwise None
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
    Get the current user ID; raise ValueError if no login context is set.

    Returns:
        str: User ID

    Raises:
        ValueError: User context is not set
    """
    uid = get_tool_uid()
    if not uid:
        raise ValueError("未登录，无法执行需要用户身份的记忆操作")
    return uid
