"""
LiteLLM Proxy gateway manager: start, health-check, and gracefully stop the Proxy process.
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
    LiteLLM Proxy gateway manager.

    Starts the Proxy subprocess in the background, polls health checks, and
    shuts down gracefully. Usable as a context manager (with-statement auto-stop).
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
        Initialize ProxyManager.

        Args:
            host (str): Proxy bind address
            port (int): Proxy bind port
            base_url (str): Base URL used for health checks
            config_path (str): LiteLLM config file path
            litellm_bin (str): Path to the litellm executable
            startup_timeout (float): Startup wait timeout in seconds
        """
        self.host = host
        self.port = port
        self.base_url = base_url
        self.config_path = config_path
        self.litellm_bin = litellm_bin
        self.startup_timeout = startup_timeout
        self._process: subprocess.Popen | None = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def is_running(self) -> bool:
        """
        Check whether the Proxy is running via /health/liveliness.

        Returns:
            bool: True if the Proxy is available, False otherwise
        """
        try:
            resp = httpx.get(f"{self.base_url}/health/liveliness", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    def start(self) -> None:
        """
        Start the LiteLLM Proxy gateway.

        Reuse an existing instance if one is already available; otherwise start a
        new background process and block until ready. A process started by this
        instance is cleaned up when Python exits.

        Returns:
            None

        Raises:
            RuntimeError: Proxy did not become ready within the timeout
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

        # Register an exit hook so a Proxy started by this instance is shut down
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
        Stop the LiteLLM Proxy subprocess started by this instance, if any.

        Returns:
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
    # Context manager support
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "ProxyManager":
        """Start the Proxy when entering a with-block."""
        self.start()
        return self

    def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
    ) -> None:
        """Stop the Proxy when exiting a with-block."""
        self.stop()

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _wait_until_ready(self) -> bool:
        """
        Poll until the Proxy health check succeeds.

        Returns:
            bool: True if ready before timeout, False if timed out
        """
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self.is_running():
                return True
            time.sleep(1.0)
        return False


# Module-level default instance, compatible with the original call style
_default_manager = ProxyManager()

start_proxy = _default_manager.start
stop_proxy = _default_manager.stop
is_proxy_running = _default_manager.is_running
