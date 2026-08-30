"""
Config APIs (RAG mode and API key read/write).
"""

import os

from fastapi import APIRouter
from pydantic import BaseModel

from src.app_settings import get_rag_mode_enabled, set_rag_mode_enabled
from src.config import ENV_PATH

router = APIRouter()

# Env var keys the frontend is allowed to read and write
ALLOWED_KEYS = [
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "TAVILY_API_KEY",
]


class RagModeRequest(BaseModel):
    """RAG mode toggle request body."""

    enabled: bool


class ApiKeysRequest(BaseModel):
    """API keys update request body."""

    keys: dict[str, str]


def _mask_value(value: str) -> str:
    """
    Mask a sensitive value for display.

    Args:
        value (str): original value

    Returns:
        str: masked string
    """
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


@router.get("/config/rag-mode")
async def get_rag_mode():
    """
    Get related-memory recall (RAG) mode status.

    Returns:
        dict: {rag_mode: bool}
    """
    return {"rag_mode": get_rag_mode_enabled()}


@router.put("/config/rag-mode")
async def set_rag_mode(req: RagModeRequest):
    """
    Set related-memory recall (RAG) mode and persist it.

    Args:
        req (RagModeRequest): toggle state

    Returns:
        dict: {rag_mode: bool}
    """
    return {"rag_mode": set_rag_mode_enabled(req.enabled)}


@router.get("/config/api-keys")
async def get_api_keys():
    """
    Read API keys from .env and return them masked.

    Returns:
        dict: mapping of key names to masked values
    """
    result: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key in ALLOWED_KEYS:
                result[key] = _mask_value(val.strip().strip('"').strip("'"))
    for key in ALLOWED_KEYS:
        result.setdefault(key, _mask_value(os.environ.get(key, "")))
    return result


@router.put("/config/api-keys")
async def set_api_keys(req: ApiKeysRequest):
    """
    Update changed API keys in .env.

    Args:
        req (ApiKeysRequest): key-value pairs

    Returns:
        dict: updated masked key-value mapping
    """
    env_lines: list[str] = []
    existing: dict[str, str] = {}

    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _, val = stripped.partition("=")
                existing[key.strip()] = val.strip()
            env_lines.append(line)

    for key, val in req.keys.items():
        if key not in ALLOWED_KEYS:
            continue
        if val and "*" not in val:
            existing[key] = val

    new_content = "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text(new_content, encoding="utf-8")

    for key, val in existing.items():
        os.environ[key] = val.strip('"').strip("'")

    masked: dict[str, str] = {}
    for key in ALLOWED_KEYS:
        masked[key] = _mask_value(existing.get(key, os.environ.get(key, "")))
    return masked
