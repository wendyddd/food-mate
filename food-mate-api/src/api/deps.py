"""
FastAPI dependency injection for Web API user authentication.
"""

from fastapi import Header, HTTPException

from src.user_auth import UserRecord, get_user_by_session


async def get_current_user(
    x_user_session: str | None = Header(default=None, alias="X-User-Session"),
) -> UserRecord:
    """
    Parse and validate the current logged-in user from request headers.

    Args:
        x_user_session (str | None): URL session identifier

    Returns:
        UserRecord: current user record

    Raises:
        HTTPException: not logged in or session is invalid
    """
    if not x_user_session or not x_user_session.strip():
        raise HTTPException(status_code=401, detail="Missing user session")

    user = get_user_by_session(x_user_session.strip())
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return user
