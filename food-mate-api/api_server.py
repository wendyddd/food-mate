"""
food-mate-api 的 FastAPI 启动入口（uvicorn）。
"""

import logging
import os

import uvicorn

from src.api.app import app


def _configure_logging() -> None:
    """
    配置应用日志，确保 agent/chat 耗时打点写入 stdout（由 start.sh 重定向到日志文件）。

    返回:
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
    # 业务模块显式设为 INFO，避免被 uvicorn 默认级别吞掉
    for name in ("src.agent", "src.api.routes.chat", "src.llm_client"):
        logging.getLogger(name).setLevel(logging.INFO)


def main() -> None:
    """
    启动 FastAPI 服务器。

    环境变量:
        FOODMATE_API_PORT (str): 服务端口，默认 8000
        FOODMATE_API_HOST (str): 监听地址，默认 0.0.0.0；生产建议 127.0.0.1
    """
    _configure_logging()
    host = os.environ.get("FOODMATE_API_HOST", "0.0.0.0")
    port = int(os.environ.get("FOODMATE_API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
