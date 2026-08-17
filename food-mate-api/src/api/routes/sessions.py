"""
Web 聊天会话 CRUD API。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.chat_session import (
    create_session,
    delete_session,
    get_raw_messages,
    load_history,
    list_sessions,
    rename_session,
    update_title,
)
from src.llm_client import LLMClient
from src.prompts import build_agent_system_prompt
from src.user_auth import UserRecord

router = APIRouter()


class RenameRequest(BaseModel):
    """重命名会话请求体。"""

    title: str


@router.get("/sessions")
async def api_list_sessions(user: UserRecord = Depends(get_current_user)):
    """
    列出当前用户的所有 Web 聊天会话。

    返回:
        dict: {sessions: [...]}
    """
    return {"sessions": list_sessions(user.uid)}


@router.post("/sessions")
async def api_create_session(user: UserRecord = Depends(get_current_user)):
    """
    创建新的空会话。

    返回:
        dict: 会话元信息
    """
    return create_session(user.uid)


@router.put("/sessions/{session_id}")
async def api_rename_session(
    session_id: str,
    req: RenameRequest,
    user: UserRecord = Depends(get_current_user),
):
    """
    重命名会话。

    参数:
        session_id (str): 会话 ID
        req (RenameRequest): 新标题

    返回:
        dict: 更新后的 id 与 title
    """
    try:
        rename_session(user.uid, session_id, req.title)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"id": session_id, "title": req.title}


@router.delete("/sessions/{session_id}")
async def api_delete_session(
    session_id: str,
    user: UserRecord = Depends(get_current_user),
):
    """
    删除会话。

    参数:
        session_id (str): 会话 ID

    返回:
        dict: 删除状态
    """
    if not delete_session(user.uid, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "id": session_id}


@router.get("/sessions/{session_id}/messages")
async def api_get_raw_messages(
    session_id: str,
    user: UserRecord = Depends(get_current_user),
):
    """
    获取含 system prompt 的完整原始消息列表。

    参数:
        session_id (str): 会话 ID

    返回:
        dict: session_id、title、messages
    """
    data = get_raw_messages(user.uid, session_id)
    system_prompt = build_agent_system_prompt(user.uid)
    all_messages = [{"role": "system", "content": system_prompt}] + data.get(
        "messages", []
    )
    return {
        "session_id": session_id,
        "title": data.get("title", ""),
        "messages": all_messages,
    }


@router.get("/sessions/{session_id}/history")
async def api_get_session_history(
    session_id: str,
    user: UserRecord = Depends(get_current_user),
):
    """
    获取会话展示用历史（不含 system prompt，含 tool_calls）。

    参数:
        session_id (str): 会话 ID

    返回:
        dict: session_id、messages
    """
    return {
        "session_id": session_id,
        "messages": load_history(user.uid, session_id),
    }


@router.post("/sessions/{session_id}/generate-title")
async def api_generate_title(
    session_id: str,
    user: UserRecord = Depends(get_current_user),
):
    """
    根据首轮对话用 LLM 生成短标题。

    参数:
        session_id (str): 会话 ID

    返回:
        dict: session_id、title
    """
    messages = load_history(user.uid, session_id)
    if not messages:
        raise HTTPException(
            status_code=400, detail="No messages to generate title from"
        )

    first_user = ""
    first_assistant = ""
    for msg in messages:
        if msg["role"] == "user" and not first_user:
            first_user = msg["content"][:200]
        elif msg["role"] == "assistant" and not first_assistant:
            first_assistant = msg["content"][:200]
        if first_user and first_assistant:
            break

    if not first_user:
        raise HTTPException(status_code=400, detail="No user message found")

    try:
        llm = LLMClient()
        prompt = (
            "Based on the conversation below, generate a short session title (max 10 words). "
            "Use the same language as the user message. "
            "Output only the title text, no quotes or punctuation.\n\n"
            f"User: {first_user}\n"
            f"Assistant: {first_assistant}"
        )
        result = llm.chat([{"role": "user", "content": prompt}])
        title = (result.content or "").strip().strip("\"'''")[:40]
        if not title:
            title = first_user[:10].strip()
        update_title(user.uid, session_id, title)
        return {"session_id": session_id, "title": title}
    except Exception:
        fallback = first_user[:10].strip()
        update_title(user.uid, session_id, fallback)
        return {"session_id": session_id, "title": fallback}


@router.post("/sessions/{session_id}/compress")
async def api_compress_session(
    session_id: str,
    user: UserRecord = Depends(get_current_user),
):
    """
    压缩会话历史（MVP stub：不做实际压缩）。

    参数:
        session_id (str): 会话 ID

    返回:
        dict: archived_count、remaining_count
    """
    count = len(load_history(user.uid, session_id))
    return {"archived_count": 0, "remaining_count": count}
