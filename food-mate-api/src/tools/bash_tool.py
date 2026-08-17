"""
bash 工具，在本机执行 shell 命令，带超时与输出截断保护。
"""

import re
import subprocess

from src.tools.registry import registry

# 命令执行超时时间（秒）
BASH_TIMEOUT = 60
# 输出最大字符数，超出则截断，避免回灌过多内容
MAX_OUTPUT_CHARS = 8000

# 危险命令正则黑名单：命中任意一条即拒绝执行，避免对系统造成破坏性影响
# 每个元素为 (正则模式, 风险说明)
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
    检查命令是否命中危险操作黑名单

    参数:
        command (str): 待检查的 shell 命令

    返回:
        str | None: 命中时返回风险说明，未命中返回 None
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
    执行 shell 命令

    参数:
        command (str): 要执行的 shell 命令

    返回:
        str: 命令的标准输出与标准错误合并结果（含退出码）
    """
    # 执行前进行危险操作拦截
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

    # 输出截断保护
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n...[输出过长已截断]"
    return output.strip()
