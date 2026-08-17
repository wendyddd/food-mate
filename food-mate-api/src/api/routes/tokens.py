"""
Token 统计 API，供 Raw Context 面板展示上下文占用。
"""

import tiktoken
from fastapi import APIRouter, Depends

from src.api.deps import get_current_user
from src.chat_session import load_history
from src.prompts import build_agent_system_prompt
from src.user_auth import UserRecord

router = APIRouter()

_encoder = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    """
    使用 cl100k_base 编码统计文本 token 数。

    参数:
        text (str): 待统计文本

    返回:
        int: token 数量
    """
    return len(_encoder.encode(text))


@router.get("/tokens/session/{session_id}")
async def api_get_session_token_count(
    session_id: str,
    user: UserRecord = Depends(get_current_user),
):
    """
    统计会话上下文 token 数：system prompt + 全部消息 content。

    参数:
        session_id (str): 会话 ID

    返回:
        dict: system_tokens、message_tokens、total_tokens
    """
    system_prompt = build_agent_system_prompt(user.uid)
    system_tokens = _count_tokens(system_prompt)

    message_tokens = 0
    for msg in load_history(user.uid, session_id):
        message_tokens += _count_tokens(msg.get("content", ""))

    return {
        "system_tokens": system_tokens,
        "message_tokens": message_tokens,
        "total_tokens": system_tokens + message_tokens,
    }
