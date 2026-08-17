"""
应用级可持久化设置（如 RAG 模式开关）。
"""

from __future__ import annotations

import json
import threading
from typing import Any

from src.config import PROJECT_ROOT

# 应用配置文件路径（与用户数据同属 data/，已被 .gitignore）
APP_CONFIG_PATH = PROJECT_ROOT / "data" / "app_config.json"

_lock = threading.Lock()


def _default_config() -> dict[str, Any]:
    """
    返回默认应用配置。

    返回:
        dict: 默认配置字典
    """
    return {"rag_mode": True}


def _read_config() -> dict[str, Any]:
    """
    读取应用配置文件；不存在或损坏时返回默认值。

    返回:
        dict: 配置字典
    """
    if not APP_CONFIG_PATH.exists():
        return _default_config()
    try:
        data = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_config()
        merged = _default_config()
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return _default_config()


def _write_config(data: dict[str, Any]) -> None:
    """
    将配置写入磁盘。

    参数:
        data (dict): 完整配置字典

    返回:
        None
    """
    APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_rag_mode_enabled() -> bool:
    """
    获取是否开启相关记忆召回（RAG）模式。

    返回:
        bool: True 表示按相关性筛选记忆后注入
    """
    with _lock:
        return bool(_read_config().get("rag_mode", True))


def set_rag_mode_enabled(enabled: bool) -> bool:
    """
    设置相关记忆召回（RAG）模式并持久化。

    参数:
        enabled (bool): 是否开启

    返回:
        bool: 写入后的 rag_mode 值
    """
    with _lock:
        data = _read_config()
        data["rag_mode"] = bool(enabled)
        _write_config(data)
        return bool(data["rag_mode"])
