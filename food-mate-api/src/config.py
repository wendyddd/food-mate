"""
Config loader: load .env secrets and config.yaml model routing, expose global settings.
"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Project root (parent of src)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
MEMORY_DIR = PROJECT_ROOT / "memory"

# Load .env so secrets are available as env vars for LiteLLM Proxy
load_dotenv(ENV_PATH)

# LiteLLM Proxy gateway settings
PROXY_HOST = "127.0.0.1"
PROXY_PORT = int(os.environ.get("PROXY_PORT", "4000"))
PROXY_BASE_URL = f"http://{PROXY_HOST}:{PROXY_PORT}"
# Must match general_settings.master_key in config.yaml; OpenAI SDK uses it for auth
PROXY_MASTER_KEY = os.environ.get("FOODMATE_PROXY_MASTER_KEY", "sk-foodmate-local")

# When set to 1/true in production, disable high-risk tools such as bash and python_repl
_DISABLE_DANGEROUS = (
    os.environ.get("FOODMATE_DISABLE_DANGEROUS_TOOLS", "").strip().lower()
)
DISABLE_DANGEROUS_TOOLS = _DISABLE_DANGEROUS in ("1", "true", "yes", "on")

# Default model (matches model_name in config.yaml)
DEFAULT_MODEL = "deepseek"


def load_model_config() -> dict:
    """
    Read config.yaml contents.

    Returns:
        dict: Parsed full YAML config dictionary
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_available_models() -> list[str]:
    """
    List all available model names from config.yaml.

    Returns:
        list[str]: model_name list, e.g. ["gpt", "claude", "deepseek"]
    """
    config = load_model_config()
    return [item["model_name"] for item in config.get("model_list", [])]
