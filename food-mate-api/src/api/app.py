"""
food-mate-api 的 FastAPI 应用入口，负责注册路由与 CORS 跨域配置。
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.auth import router as auth_router
from src.api.routes.chat import router as chat_router
from src.api.routes.config import router as config_router
from src.api.routes.files import router as files_router
from src.api.routes.memory import router as memory_router
from src.api.routes.sessions import router as sessions_router
from src.api.routes.tokens import router as tokens_router

# 默认允许本地开发与正式域名；可用 FOODMATE_CORS_ORIGINS 覆盖（逗号分隔）
_DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://foodmates365.com",
    "https://www.foodmates365.com",
]


def _load_cors_origins() -> list[str]:
    """
    从环境变量加载 CORS 允许来源列表。

    环境变量:
        FOODMATE_CORS_ORIGINS (str): 逗号分隔的 Origin 列表；未设置则用默认值

    返回:
        list[str]: 允许的 Origin 列表
    """
    raw = os.environ.get("FOODMATE_CORS_ORIGINS", "").strip()
    if not raw:
        return list(_DEFAULT_CORS_ORIGINS)
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_app() -> FastAPI:
    """
    创建 FastAPI 应用实例。

    返回:
        FastAPI: 应用实例
    """
    app = FastAPI(title="food-mate-api", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_load_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix="/api")
    app.include_router(files_router, prefix="/api")
    app.include_router(memory_router, prefix="/api/memory")
    app.include_router(chat_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(config_router, prefix="/api")
    app.include_router(tokens_router, prefix="/api")

    return app


app = create_app()
