"""
配置相关 API（RAG 模式、API Keys 读写）。
"""

import os

from fastapi import APIRouter
from pydantic import BaseModel

from src.app_settings import get_rag_mode_enabled, set_rag_mode_enabled
from src.config import ENV_PATH

router = APIRouter()

# 允许前端读写的环境变量键
ALLOWED_KEYS = [
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "TAVILY_API_KEY",
]


class RagModeRequest(BaseModel):
    """RAG 模式开关请求体。"""

    enabled: bool


class ApiKeysRequest(BaseModel):
    """API Keys 更新请求体。"""

    keys: dict[str, str]


def _mask_value(value: str) -> str:
    """
    对敏感值做脱敏展示。

    参数:
        value (str): 原始值

    返回:
        str: 脱敏后的字符串
    """
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


@router.get("/config/rag-mode")
async def get_rag_mode():
    """
    获取相关记忆召回（RAG）模式状态。

    返回:
        dict: {rag_mode: bool}
    """
    return {"rag_mode": get_rag_mode_enabled()}


@router.put("/config/rag-mode")
async def set_rag_mode(req: RagModeRequest):
    """
    设置相关记忆召回（RAG）模式并持久化。

    参数:
        req (RagModeRequest): 开关状态

    返回:
        dict: {rag_mode: bool}
    """
    return {"rag_mode": set_rag_mode_enabled(req.enabled)}


@router.get("/config/api-keys")
async def get_api_keys():
    """
    读取 .env 中的 API Keys 并脱敏返回。

    返回:
        dict: 键名到脱敏值的映射
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
    更新 .env 中变更过的 API Keys。

    参数:
        req (ApiKeysRequest): 键值对

    返回:
        dict: 更新后脱敏的键值映射
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
