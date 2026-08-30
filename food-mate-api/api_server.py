"""
FastAPI entry point for food-mate-api (uvicorn).
"""

import logging
import os

import uvicorn

from src.api.app import app


def _configure_logging() -> None:
    """
    Configure app logging so agent/chat timing logs go to stdout
    (redirected to a log file by start.sh).

    Returns:
        None
    """
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        root.setLevel(logging.INFO)
    # Set business modules to INFO so uvicorn's default level does not hide them
    for name in ("src.agent", "src.api.routes.chat", "src.llm_client"):
        logging.getLogger(name).setLevel(logging.INFO)


def main() -> None:
    """
    Start the FastAPI server.

    Environment variables:
        FOODMATE_API_PORT (str): Service port, default 8000
        FOODMATE_API_HOST (str): Bind address, default 0.0.0.0; use 127.0.0.1 in production
    """
    _configure_logging()
    host = os.environ.get("FOODMATE_API_HOST", "0.0.0.0")
    port = int(os.environ.get("FOODMATE_API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
