"""
App-level persistent settings (e.g. RAG mode toggle).
"""

from __future__ import annotations

import json
import threading
from typing import Any

from src.config import PROJECT_ROOT

# App config file path (under data/, same as user data; gitignored)
APP_CONFIG_PATH = PROJECT_ROOT / "data" / "app_config.json"

_lock = threading.Lock()


def _default_config() -> dict[str, Any]:
    """
    Return the default app config.

    Returns:
        dict: Default config dictionary
    """
    return {"rag_mode": True}


def _read_config() -> dict[str, Any]:
    """
    Read the app config file; return defaults if missing or corrupt.

    Returns:
        dict: Config dictionary
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
    Write config to disk.

    Args:
        data (dict): Full config dictionary

    Returns:
        None
    """
    APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_rag_mode_enabled() -> bool:
    """
    Return whether relevant-memory recall (RAG) mode is enabled.

    Returns:
        bool: True means inject memories after relevance filtering
    """
    with _lock:
        return bool(_read_config().get("rag_mode", True))


def set_rag_mode_enabled(enabled: bool) -> bool:
    """
    Set relevant-memory recall (RAG) mode and persist it.

    Args:
        enabled (bool): Whether to enable

    Returns:
        bool: rag_mode value after write
    """
    with _lock:
        data = _read_config()
        data["rag_mode"] = bool(enabled)
        _write_config(data)
        return bool(data["rag_mode"])
