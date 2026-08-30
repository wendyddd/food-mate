"""
File read/write endpoints for the frontend editor to load and save memory files.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.memory import read_memory_file, save_memory_file
from src.user_auth import UserRecord

router = APIRouter()


class FileSaveRequest(BaseModel):
    """Save-file request body."""

    path: str
    content: str


@router.get("/files")
async def read_file(path: str, user: UserRecord = Depends(get_current_user)):
    """
    Read file content under the memory directory.

    Args:
        path (str): relative file path

    Returns:
        dict: {path, content}
    """
    normalized = path.replace("\\", "/").lstrip("./")
    if not normalized.startswith("memory/"):
        raise HTTPException(status_code=403, detail=f"Access denied: {path}")
    try:
        content = read_memory_file(normalized, user.uid)
        return {"path": path, "content": content}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")


@router.post("/files")
async def save_file(
    request: FileSaveRequest,
    user: UserRecord = Depends(get_current_user),
):
    """
    Save file content under the memory directory.

    Args:
        request (FileSaveRequest): path and content

    Returns:
        dict: {path, status}
    """
    normalized = request.path.replace("\\", "/").lstrip("./")
    if not normalized.startswith("memory/"):
        raise HTTPException(status_code=403, detail=f"Access denied: {request.path}")
    try:
        save_memory_file(normalized, request.content, user.uid)
        return {"path": request.path, "status": "saved"}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
