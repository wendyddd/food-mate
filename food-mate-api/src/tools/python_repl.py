"""
python_repl tool: run a Python snippet in an isolated subprocess and capture output.
"""

import subprocess
import sys

from src.tools.registry import registry

# Code execution timeout (seconds)
PYTHON_TIMEOUT = 30
# Max output characters
MAX_OUTPUT_CHARS = 8000


@registry.register(
    name="python_repl",
    description="Run Python code in an isolated subprocess and return stdout/stderr. Use print() for output. Good for math and data.",
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code snippet; use print() for results",
            }
        },
        "required": ["code"],
    },
)
def python_repl(code: str) -> str:
    """
    Run Python code in a subprocess.

    Args:
        code (str): Python snippet to execute

    Returns:
        str: stdout and stderr from the run, or an error message on failure
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=PYTHON_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"[python_repl 超时] 代码执行超过 {PYTHON_TIMEOUT} 秒被终止"

    output = result.stdout or ""
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"

    if not output.strip():
        output = "[无输出] 代码已执行但未产生 stdout/stderr，请使用 print 输出结果。"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n...[输出过长已截断]"
    return output.strip()
