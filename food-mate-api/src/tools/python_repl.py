"""
python_repl 工具，在独立子进程中执行 Python 代码片段并捕获输出。
"""

import subprocess
import sys

from src.tools.registry import registry

# 代码执行超时时间（秒）
PYTHON_TIMEOUT = 30
# 输出最大字符数
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
    在子进程中执行 Python 代码

    参数:
        code (str): 要执行的 Python 代码片段

    返回:
        str: 代码执行的 stdout 与 stderr，失败时返回错误提示
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
