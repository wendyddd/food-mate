"""
bash tool: run shell commands locally, with timeout and output truncation.
"""

import re
import subprocess

from src.tools.registry import registry

# Command execution timeout (seconds)
BASH_TIMEOUT = 60
# Max output characters; truncate beyond this to avoid flooding context
MAX_OUTPUT_CHARS = 8000

# Regex blacklist of dangerous commands; any match is rejected to avoid destructive effects
# Each item is (regex pattern, risk description)
DANGEROUS_PATTERNS = [
    (
        r"\brm\s+(-[a-zA-Z]*\s+)*(-[a-zA-Z]*[rf][a-zA-Z]*)\s",
        "递归/强制删除文件 (rm -rf)",
    ),
    (r"\brm\s+-[a-zA-Z]*[rf]", "递归/强制删除文件 (rm -rf)"),
    (r":\(\)\s*\{.*\}\s*;", "fork 炸弹"),
    (r">\s*/dev/sd[a-z]", "直接写入磁盘设备"),
    (r"\bdd\b.*\bof=/dev/", "dd 覆写磁盘设备"),
    (r"\bmkfs(\.\w+)?\b", "格式化文件系统"),
    (r"\b(shutdown|reboot|halt|poweroff|init\s+0|init\s+6)\b", "关机/重启系统"),
    (r"\b(chmod|chown)\s+(-[a-zA-Z]*\s+)*.*\s+/(?:\s|$)", "对根目录递归修改权限/属主"),
    (r"\brm\s+(-[a-zA-Z]*\s+)*/(?:\s|$|\*)", "删除根目录"),
    (r">\s*/etc/", "覆写系统关键配置文件"),
    (r"\b(curl|wget)\b.*\|\s*(sudo\s+)?(bash|sh|zsh)\b", "下载并直接执行远程脚本"),
    (r"\bsudo\b", "提权执行 (sudo)"),
    (r"\bmv\s+.*\s+/dev/null\b", "将文件移动到 /dev/null 销毁数据"),
    (r"\b(userdel|groupdel|passwd|deluser)\b", "修改/删除系统用户"),
]


def check_dangerous(command: str) -> str | None:
    """
    Check whether a command matches the dangerous-operation blacklist.

    Args:
        command (str): shell command to check

    Returns:
        str | None: risk description if matched, otherwise None
    """
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            return reason
    return None


@registry.register(
    name="bash",
    description="Run a shell command locally and return stdout and stderr. For listing files, scripts, and system tasks.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute",
            }
        },
        "required": ["command"],
    },
)
def bash(command: str) -> str:
    """
    Execute a shell command.

    Args:
        command (str): shell command to run

    Returns:
        str: combined stdout and stderr (including exit code)
    """
    # Intercept dangerous operations before execution
    reason = check_dangerous(command)
    if reason is not None:
        return f"[已拦截危险命令] 检测到风险操作（{reason}），出于安全考虑拒绝执行：{command}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=BASH_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"[bash 超时] 命令执行超过 {BASH_TIMEOUT} 秒被终止：{command}"

    output = result.stdout or ""
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    output += f"\n[exit_code] {result.returncode}"

    # Truncate oversized output
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n...[输出过长已截断]"
    return output.strip()
