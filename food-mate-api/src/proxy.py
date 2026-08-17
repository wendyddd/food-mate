"""
LiteLLM Proxy 网关管理模块，封装 Proxy 进程的启动、健康检查与优雅关闭。
"""

import atexit
import subprocess
import sys
import time
from types import TracebackType

import httpx
from pathlib import Path
from src.config import CONFIG_PATH, PROXY_BASE_URL, PROXY_HOST, PROXY_PORT

_LITELLM_BIN = str(Path(sys.executable).parent / "litellm")


class ProxyManager:
    """
    LiteLLM Proxy 网关管理器。

    负责后台拉起 Proxy 子进程、轮询健康检查、优雅关闭，
    支持作为 context manager 使用（with 语句自动停止）。
    """

    def __init__(
            self,
            host: str = PROXY_HOST,
            port: int = PROXY_PORT,
            base_url: str = PROXY_BASE_URL,
            config_path: str = str(CONFIG_PATH),
            litellm_bin: str = _LITELLM_BIN,
            startup_timeout: float = 60.0,
    ) -> None:
        """
        初始化 ProxyManager

        参数:
            host (str): Proxy 监听地址
            port (int): Proxy 监听端口
            base_url (str): 健康检查所用的基础 URL
            config_path (str): LiteLLM 配置文件路径
            litellm_bin (str): litellm 可执行文件路径
            startup_timeout (float): 启动等待超时秒数
        """
        self.host = host
        self.port = port
        self.base_url = base_url
        self.config_path = config_path
        self.litellm_bin = litellm_bin
        self.startup_timeout = startup_timeout
        self._process: subprocess.Popen | None = None

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #

    def is_running(self) -> bool:
        """
        通过 /health/liveliness 接口检测 Proxy 是否已在运行

        返回:
            bool: True 表示 Proxy 已可用，False 表示不可用
        """
        try:
            resp = httpx.get(f"{self.base_url}/health/liveliness", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    def start(self) -> None:
        """
        启动 LiteLLM Proxy 网关。

        若已有可用实例则直接复用；否则后台拉起新进程并阻塞等待就绪。
        由本实例拉起的进程会在 Python 退出时自动清理。

        返回:
            None

        抛出:
            RuntimeError: Proxy 在超时内未能就绪
        """
        if self.is_running():
            print(f"[proxy] 已检测到运行中的 LiteLLM Proxy，直接复用：{self.base_url}")
            return

        print(f"[proxy] 正在后台启动 LiteLLM Proxy（{self.host}:{self.port}）...")
        self._process = subprocess.Popen(
            [
                self.litellm_bin,
                "--config",
                self.config_path,
                "--host",
                self.host,
                "--port",
                str(self.port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[proxy] proxy_process pid: {self._process.pid}")

        # 注册退出钩子，确保由本实例拉起的 Proxy 被关闭
        atexit.register(self.stop)

        if not self._wait_until_ready():
            self.stop()
            print(
                "[proxy] LiteLLM Proxy 启动超时，请检查 config.yaml 与依赖。",
                file=sys.stderr,
            )
            raise RuntimeError("LiteLLM Proxy 启动失败")

        print(f"[proxy] LiteLLM Proxy 已就绪：{self.base_url}")

    def stop(self) -> None:
        """
        关闭由本实例拉起的 LiteLLM Proxy 子进程（若存在）

        返回:
            None
        """
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    # ------------------------------------------------------------------ #
    # Context manager 支持
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "ProxyManager":
        """进入 with 块时自动启动 Proxy"""
        self.start()
        return self

    def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
    ) -> None:
        """退出 with 块时自动停止 Proxy"""
        self.stop()

    # ------------------------------------------------------------------ #
    # 私有辅助
    # ------------------------------------------------------------------ #

    def _wait_until_ready(self) -> bool:
        """
        轮询等待 Proxy 健康检查通过

        返回:
            bool: True 表示在超时前就绪，False 表示超时
        """
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self.is_running():
                return True
            time.sleep(1.0)
        return False


# 模块级默认实例，保持与原有调用方式兼容
_default_manager = ProxyManager()

start_proxy = _default_manager.start
stop_proxy = _default_manager.stop
is_proxy_running = _default_manager.is_running
