"""
Memory-system API routes: structured entry CRUD, Markdown view, and extract-from-session.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.chat_session import (
    get_latest_session_content,
    get_session_content,
    list_sessions,
    load_history,
)
from src.memory import (
    add_entry,
    delete_entry,
    list_entries,
    list_memory_files,
    load_context,
    patch_entries_source,
    save_user,
    update_entry,
)
from src.memory_extractor import extract_and_merge_user_from_session
from src.memory_schema import MemorySourceContext
from src.user_auth import UserRecord

router = APIRouter()


class MemoryUserWriteRequest(BaseModel):
    """Request body for writing user.md."""

    content: str


class ExtractRequest(BaseModel):
    """Request body to extract and update memory from a Web chat session."""

    session_id: Optional[str] = None
    model: Optional[str] = None


class MemoryEntryCreateRequest(BaseModel):
    """Request body for creating a memory entry."""

    category: str
    content: str


class MemoryEntryUpdateRequest(BaseModel):
    """Request body for updating a memory entry."""

    content: str
    category: Optional[str] = None


@router.get("/files")
async def get_memory_files(user: UserRecord = Depends(get_current_user)):
    """
    List editable memory files.

    Returns:
        dict: {files: ...}
    """
    return {"files": list_memory_files(user.uid)}


@router.get("/entries")
async def get_memory_entries(user: UserRecord = Depends(get_current_user)):
    """
    List all structured memory entries.

    Returns:
        dict: {entries: [...]}
    """
    entries = list_entries(user.uid)
    return {"entries": [e.to_dict() for e in entries]}


@router.post("/entries")
async def post_memory_entry(
    req: MemoryEntryCreateRequest,
    user: UserRecord = Depends(get_current_user),
):
    """
    Create a memory entry.

    Args:
        req (MemoryEntryCreateRequest): category and content

    Returns:
        dict: {entry: ...}
    """
    try:
        entry = add_entry(user.uid, req.category, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"entry": entry.to_dict()}


@router.put("/entries/{entry_id}")
async def put_memory_entry(
    entry_id: str,
    req: MemoryEntryUpdateRequest,
    user: UserRecord = Depends(get_current_user),
):
    """
    Update a memory entry.

    Args:
        entry_id (str): entry ID
        req (MemoryEntryUpdateRequest): new content

    Returns:
        dict: {entry: ...}
    """
    try:
        entry = update_entry(user.uid, entry_id, req.content, category=req.category)
    except ValueError as e:
        # Empty content / invalid category → 400; entry not found → 404
        detail = str(e)
        status = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail) from e
    return {"entry": entry.to_dict()}


@router.delete("/entries/{entry_id}")
async def remove_memory_entry(
    entry_id: str,
    user: UserRecord = Depends(get_current_user),
):
    """
    Delete a memory entry.

    Args:
        entry_id (str): entry ID

    Returns:
        dict: {status: "deleted"}
    """
    if not delete_entry(user.uid, entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"status": "deleted"}


@router.get("/user")
async def get_user_memory(user: UserRecord = Depends(get_current_user)):
    """
    Read the current long-term profile as a Markdown export.

    Returns:
        dict: {content: str}
    """
    return {"content": load_context(user.uid)}


@router.put("/user")
async def put_user_memory(
    req: MemoryUserWriteRequest,
    user: UserRecord = Depends(get_current_user),
):
    """
    Overwrite memory from Markdown (parsed into entries).

    Args:
        req (MemoryUserWriteRequest): request body

    Returns:
        dict: {status: "saved"}
    """
    save_user(req.content, user.uid)
    return {"status": "saved"}


@router.post("/extract")
async def extract_memory(
    req: ExtractRequest,
    user: UserRecord = Depends(get_current_user),
):
    """
    Extract preference updates from a Web chat session and merge them into structured memory.

    Args:
        req (ExtractRequest): session_id and model

    Returns:
        dict: {changed, user, entries}
    """
    current_user = load_context(user.uid)
    old_ids = {e.id for e in list_entries(user.uid)}

    if req.session_id:
        session_content = get_session_content(user.uid, req.session_id)
        session_id_used = req.session_id
        if not session_content.strip():
            raise HTTPException(status_code=400, detail="Session not found or empty")
    else:
        sessions = list_sessions(user.uid)
        session_id_used = sessions[0]["id"] if sessions else None
        session_content = get_latest_session_content(user.uid)

    if not session_content.strip():
        raise HTTPException(status_code=400, detail="No session content found")

    result = extract_and_merge_user_from_session(
        session_content,
        current_user,
        model=req.model or None or "deepseek",
    )
    if result.changed:
        save_user(result.updated_user_markdown, user.uid)
        new_ids = [e.id for e in list_entries(user.uid) if e.id not in old_ids]
        quote = ""
        if session_id_used:
            for msg in reversed(load_history(user.uid, session_id_used)):
                if msg.get("role") == "user" and (msg.get("content") or "").strip():
                    quote = (msg.get("content") or "").strip()
                    break
        patch_entries_source(
            user.uid,
            new_ids,
            MemorySourceContext(
                source_type="extract",
                source_session_id=session_id_used,
                source_quote=quote or None,
            ),
        )
    entries = list_entries(user.uid)
    return {
        "changed": result.changed,
        "user": result.updated_user_markdown,
        "entries": [e.to_dict() for e in entries],
    }
