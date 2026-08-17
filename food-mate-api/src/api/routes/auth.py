"""
用户登录与 session 校验 API。
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
    """登录请求体。"""

    uid: str
    pwd: str


@router.get("/health")
async def health():
    """
    服务健康检查（无需登录）。

    返回:
        dict: {status: ok}
    """
    return {"status": "ok"}


@router.post("/auth/login")
async def login(req: LoginRequest):
    """
    使用 uid 与密码登录。

    参数:
        req (LoginRequest): 登录凭据

    返回:
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
    校验 URL session 是否合法。

    参数:
        user_session (str): CSV 中的 session 标识

    返回:
        dict: {uid, session}
    """
    user = get_user_by_session(user_session)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return public_user_info(user)
