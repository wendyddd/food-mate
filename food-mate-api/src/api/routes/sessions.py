"""
Web chat session CRUD API.
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
    """Rename-session request body."""

    title: str


@router.get("/sessions")
async def api_list_sessions(user: UserRecord = Depends(get_current_user)):
    """
    List all Web chat sessions for the current user.

    Returns:
        dict: {sessions: [...]}
    """
    return {"sessions": list_sessions(user.uid)}


@router.post("/sessions")
async def api_create_session(user: UserRecord = Depends(get_current_user)):
    """
    Create a new empty session.

    Returns:
        dict: session metadata
    """
    return create_session(user.uid)


@router.put("/sessions/{session_id}")
async def api_rename_session(
    session_id: str,
    req: RenameRequest,
    user: UserRecord = Depends(get_current_user),
):
    """
    Rename a session.

    Args:
        session_id (str): session ID
        req (RenameRequest): new title

    Returns:
        dict: updated id and title
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
    Delete a session.

    Args:
        session_id (str): session ID

    Returns:
        dict: deletion status
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
    Get the full raw message list including the system prompt.

    Args:
        session_id (str): session ID

    Returns:
        dict: session_id, title, messages
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
    Get display history for a session (no system prompt; includes tool_calls).

    Args:
        session_id (str): session ID

    Returns:
        dict: session_id, messages
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
    Generate a short title from the first turn via LLM.

    Args:
        session_id (str): session ID

    Returns:
        dict: session_id, title
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
    Compress session history (MVP stub: no actual compression).

    Args:
        session_id (str): session ID

    Returns:
        dict: archived_count, remaining_count
    """
    count = len(load_history(user.uid, session_id))
    return {"archived_count": 0, "remaining_count": count}
