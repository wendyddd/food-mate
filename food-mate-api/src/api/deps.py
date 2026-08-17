"""
FastAPI 依赖注入，提供 Web API 用户鉴权。
"""

from fastapi import Header, HTTPException

from src.user_auth import UserRecord, get_user_by_session


async def get_current_user(
    x_user_session: str | None = Header(default=None, alias="X-User-Session"),
) -> UserRecord:
    """
    从请求头解析并校验当前登录用户。

    参数:
        x_user_session (str | None): URL session 标识

    返回:
        UserRecord: 当前用户记录

    Raises:
        HTTPException: 未登录或 session 无效
    """
    if not x_user_session or not x_user_session.strip():
        raise HTTPException(status_code=401, detail="Missing user session")

    user = get_user_by_session(x_user_session.strip())
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return user
