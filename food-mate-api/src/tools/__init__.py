"""
Tools plugin package entry: import tool modules to trigger auto-registration and expose the global registry.
"""

from src.config import DISABLE_DANGEROUS_TOOLS

# Import tool modules so @registry.register decorators run
from src.tools import file_tools  # noqa: F401
from src.tools import fetch_url  # noqa: F401
from src.tools import web_search  # noqa: F401

# Do not register tools that execute local commands in public production
if not DISABLE_DANGEROUS_TOOLS:
    from src.tools import bash_tool  # noqa: F401
    from src.tools import python_repl  # noqa: F401

from src.tools.registry import registry

__all__ = ["registry"]
