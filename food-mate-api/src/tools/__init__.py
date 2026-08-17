"""
工具插件包入口，导入各工具模块以触发自动注册，并对外暴露全局 registry。
"""

from src.config import DISABLE_DANGEROUS_TOOLS

# 导入各工具模块，触发 @registry.register 装饰器完成注册
from src.tools import file_tools  # noqa: F401
from src.tools import fetch_url  # noqa: F401
from src.tools import web_search  # noqa: F401

# 生产公网环境默认不注册可执行本机命令的工具
if not DISABLE_DANGEROUS_TOOLS:
    from src.tools import bash_tool  # noqa: F401
    from src.tools import python_repl  # noqa: F401

from src.tools.registry import registry

__all__ = ["registry"]
