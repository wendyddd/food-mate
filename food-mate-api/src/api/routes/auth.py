"""
User login and session verification API.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.user_auth import (
    authenticate,
    get_user_by_session,
    public_user_info,
    touch_last_login,
)

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request body."""

    uid: str
    pwd: str


@router.get("/health")
async def health():
    """
    Service health check (no login required).

    Returns:
        dict: {status: ok}
    """
    return {"status": "ok"}


@router.post("/auth/login")
async def login(req: LoginRequest):
    """
    Log in with uid and password.

    Args:
        req (LoginRequest): login credentials

    Returns:
        dict: {uid, session}
    """
    user = authenticate(req.uid, req.pwd)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid uid or password")
    touch_last_login(user.uid)
    return public_user_info(user)


@router.get("/auth/session/{user_session}")
async def verify_session(user_session: str):
    """
    Verify whether a URL session is valid.

    Args:
        user_session (str): session identifier from the CSV

    Returns:
        dict: {uid, session}
    """
    user = get_user_by_session(user_session)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return public_user_info(user)
