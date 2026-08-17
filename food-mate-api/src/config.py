"""
配置加载模块，负责加载 .env 敏感信息与 config.yaml 模型路由，集中暴露全局配置。
"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# 项目根目录（src 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
MEMORY_DIR = PROJECT_ROOT / "memory"

# 加载 .env，使敏感信息进入环境变量供 LiteLLM Proxy 读取
load_dotenv(ENV_PATH)

# LiteLLM Proxy 网关相关配置
PROXY_HOST = "127.0.0.1"
PROXY_PORT = int(os.environ.get("PROXY_PORT", "4000"))
PROXY_BASE_URL = f"http://{PROXY_HOST}:{PROXY_PORT}"
# 与 config.yaml 中 general_settings.master_key 保持一致，OpenAI SDK 用它鉴权
PROXY_MASTER_KEY = os.environ.get("FOODMATE_PROXY_MASTER_KEY", "sk-foodmate-local")

# 生产环境设为 1/true 时禁用 bash、python_repl 等高危工具
_DISABLE_DANGEROUS = (
    os.environ.get("FOODMATE_DISABLE_DANGEROUS_TOOLS", "").strip().lower()
)
DISABLE_DANGEROUS_TOOLS = _DISABLE_DANGEROUS in ("1", "true", "yes", "on")

# 默认使用的模型（对应 config.yaml 的 model_name）
DEFAULT_MODEL = "deepseek"


def load_model_config() -> dict:
    """
    读取 config.yaml 配置内容

    返回:
        dict: 解析后的完整 YAML 配置字典
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_available_models() -> list[str]:
    """
    获取 config.yaml 中所有可用的模型名称列表

    返回:
        list[str]: model_name 列表，例如 ["gpt", "claude", "deepseek"]
    """
    config = load_model_config()
    return [item["model_name"] for item in config.get("model_list", [])]
