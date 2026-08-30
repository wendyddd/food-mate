"""
CLI entry for FoodMate Agent: start Proxy, render chat, and handle slash commands.
"""

import getpass

from rich.console import Console
from rich.panel import Panel

from src.agent import Agent
from src.config import DEFAULT_MODEL, MEMORY_DIR, list_available_models
from src.memory import get_user_path, load_context
from src.proxy import start_proxy
from src.user_auth import authenticate, touch_last_login

console = Console()

# Help text
HELP_TEXT = """可用命令：
  /model <名称>   切换模型（可选：{models}）
  /reset          清空当前对话上下文（保留长期记忆）
  /memory         查看长期记忆档案
  /help           显示本帮助
  /exit           退出程序
"""


def print_tool_event(label: str, payload: str) -> None:
    """
    Print a tool-call progress event.

    Args:
        label (str): Tool name, or a label with a "-> result" suffix
        payload (str): Arguments or result text

    Returns:
        None
    """
    # Results can be long; truncate for display
    shown = payload if len(payload) <= 500 else payload[:500] + " ...[截断]"
    console.print(f"[dim]🔧 {label}: {shown}[/dim]")


def handle_command(cmd: str, agent: Agent) -> bool:
    """
    Handle a slash command.

    Args:
        cmd (str): User command (starts with /)
        agent (Agent): Current Agent instance

    Returns:
        bool: True to keep running, False to exit
    """
    parts = cmd.strip().split(maxsplit=1)
    name = parts[0].lower()

    if name == "/exit":
        return False

    if name == "/help":
        console.print(HELP_TEXT.format(models=", ".join(list_available_models())))
        return True

    if name == "/reset":
        agent.reset()
        console.print("[green]已清空对话上下文。[/green]")
        return True

    if name == "/memory":
        context = load_context(agent.uid)
        console.print(Panel(context or "（暂无记忆）", title="长期记忆档案"))
        return True

    if name == "/model":
        if len(parts) < 2:
            console.print("[yellow]用法：/model <名称>[/yellow]")
            return True
        target = parts[1].strip()
        available = list_available_models()
        if target not in available:
            console.print(f"[red]未知模型 {target}，可选：{', '.join(available)}[/red]")
            return True
        agent.set_model(target)
        console.print(f"[green]已切换模型为 {target}。[/green]")
        return True

    console.print(f"[yellow]未知命令 {name}，输入 /help 查看帮助。[/yellow]")
    return True


def prompt_login() -> str:
    """
    CLI login: verify uid and password.

    Returns:
        str: User ID after successful login

    Raises:
        SystemExit: Login failed or user cancelled
    """
    console.print("[bold]请先登录[/bold]（凭据来自 data/user_info.csv）")
    try:
        uid = console.input("[bold green]UID > [/bold green]").strip()
        pwd = getpass.getpass("密码 > ")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[cyan]已取消登录。[/cyan]")
        raise SystemExit(0) from None

    user = authenticate(uid, pwd)
    if not user:
        console.print("[red]登录失败：UID 或密码错误。[/red]")
        raise SystemExit(1)

    touch_last_login(user.uid)
    console.print(f"[green]登录成功，欢迎 {user.uid}。[/green]")
    return user.uid


def main() -> None:
    """
    Program entry: start Proxy, initialize Agent, and enter the chat loop.

    Returns:
        None
    """
    console.print(
        Panel.fit(
            "[bold cyan]FoodMate Agent[/bold cyan]\n"
            "你的家庭烹饪助手：选菜、跟步骤、搞定厨房问题 🍳\n"
            "输入 [bold]/help[/bold] 查看命令，[bold]/exit[/bold] 退出。",
            border_style="cyan",
        )
    )

    # Start LiteLLM Proxy gateway
    try:
        start_proxy()
    except Exception as e:
        console.print(f"[red]Proxy 启动失败：{e}[/red]")
        return

    uid = prompt_login()
    agent = Agent(uid=uid, model=DEFAULT_MODEL)
    user_md = get_user_path(uid)
    console.print(
        f"[dim]当前模型：{agent.model} ｜ 记忆目录：{MEMORY_DIR} ｜ 档案：{user_md}[/dim]\n"
    )

    while True:
        try:
            user_input = console.input("[bold green]你 > [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[cyan]再见，记得好好吃饭！[/cyan]")
            break

        if not user_input:
            continue

        # Slash-command handling
        if user_input.startswith("/"):
            if not handle_command(user_input, agent):
                console.print("[cyan]再见，记得好好吃饭！[/cyan]")
                break
            continue

        # Normal conversation
        try:
            console.print("[bold cyan]FoodMate >[/bold cyan]")
            reply = agent.invoke(
                user_input,
                on_tool=print_tool_event,
                on_token=lambda t: console.print(t, end=""),
            )
            console.print()
            console.print()
        except Exception as e:
            console.print(f"[red]出错了：{e}[/red]")
            continue

        if not reply.strip():
            console.print()
            continue


if __name__ == "__main__":
    main()
