"""
记忆系统 API 路由，提供结构化条目 CRUD、Markdown 视图与从会话提取能力。
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
    """写入 user.md 请求体。"""

    content: str


class ExtractRequest(BaseModel):
    """从 Web 聊天会话提取并更新记忆的请求体。"""

    session_id: Optional[str] = None
    model: Optional[str] = None


class MemoryEntryCreateRequest(BaseModel):
    """新增记忆条目请求体。"""

    category: str
    content: str


class MemoryEntryUpdateRequest(BaseModel):
    """更新记忆条目请求体。"""

    content: str
    category: Optional[str] = None


@router.get("/files")
async def get_memory_files(user: UserRecord = Depends(get_current_user)):
    """
    获取可编辑的记忆文件清单。

    返回:
        dict: {files: ...}
    """
    return {"files": list_memory_files(user.uid)}


@router.get("/entries")
async def get_memory_entries(user: UserRecord = Depends(get_current_user)):
    """
    获取全部结构化记忆条目。

    返回:
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
    新增一条记忆条目。

    参数:
        req (MemoryEntryCreateRequest): 分区与内容

    返回:
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
    更新指定记忆条目。

    参数:
        entry_id (str): 条目 ID
        req (MemoryEntryUpdateRequest): 新内容

    返回:
        dict: {entry: ...}
    """
    try:
        entry = update_entry(user.uid, entry_id, req.content, category=req.category)
    except ValueError as e:
        # 内容为空 / 分类非法 → 400；条目不存在 → 404
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
    删除指定记忆条目。

    参数:
        entry_id (str): 条目 ID

    返回:
        dict: {status: "deleted"}
    """
    if not delete_entry(user.uid, entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"status": "deleted"}


@router.get("/user")
async def get_user_memory(user: UserRecord = Depends(get_current_user)):
    """
    读取当前长期画像 Markdown 导出视图。

    返回:
        dict: {content: str}
    """
    return {"content": load_context(user.uid)}


@router.put("/user")
async def put_user_memory(
    req: MemoryUserWriteRequest,
    user: UserRecord = Depends(get_current_user),
):
    """
    从 Markdown 覆盖写入记忆（解析为 entries）。

    参数:
        req (MemoryUserWriteRequest): 请求体

    返回:
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
    将 Web 聊天会话中的偏好更新提取并合并进结构化记忆。

    参数:
        req (ExtractRequest): session_id 与 model

    返回:
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
