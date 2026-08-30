"""
FastAPI application entry for food-mate-api; registers routes and CORS.
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

# Default origins for local development and production; override with FOODMATE_CORS_ORIGINS (comma-separated)
_DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://foodmates365.com",
    "https://www.foodmates365.com",
]


def _load_cors_origins() -> list[str]:
    """
    Load the CORS allowed-origins list from the environment.

    Environment:
        FOODMATE_CORS_ORIGINS (str): comma-separated Origin list; uses defaults if unset

    Returns:
        list[str]: allowed Origin list
    """
    raw = os.environ.get("FOODMATE_CORS_ORIGINS", "").strip()
    if not raw:
        return list(_DEFAULT_CORS_ORIGINS)
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_app() -> FastAPI:
    """
    Create a FastAPI application instance.

    Returns:
        FastAPI: application instance
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
