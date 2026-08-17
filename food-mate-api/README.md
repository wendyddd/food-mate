# 美食伙伴 Agent（Food Mate）

一个贴心的**家庭烹饪助手**。围绕在家做菜，帮助用户根据口味与厨房条件选菜、跟步骤做菜、灵活替换食材——提供菜谱推荐、用量与步骤指导、烹饪技巧，并通过长期记忆记住个人偏好。

## 架构概览

```
CLI (main.py)
  └─ Agent (src/agent.py)
       ├─ LLM Client (src/llm_client.py)  ── OpenAI SDK
       │     └─ LiteLLM Proxy :4000 (src/proxy.py，自动后台拉起)
       │            └─ 多厂商模型（deepseek / gpt / claude，见 config.yaml）
       ├─ Tool Registry (src/tools/registry.py)
       │     └─ bash / read_file / write_file / fetch_url / web_search / python_repl
       └─ Memory (src/memory.py)  ── Markdown 文件记忆
```

- `.env`：存储所有敏感信息（各厂商 API Key、搜索 Key 等）。
- `config.yaml`：定义模型与路由，供 LiteLLM Proxy 使用。
- LiteLLM Proxy 作为统一 LLM API 网关，程序启动时自动在后台拉起。
- OpenAI SDK 通过 Proxy 统一读取、管理、路由多厂商大模型。

## 环境要求

- 指定 conda 环境：`/opt/miniconda3/envs/py311`（Python 3.11）
- 依赖见 `requirements.txt`

安装依赖（注意 LiteLLM 需要 `[proxy]` 额外依赖才能启动网关）：

```bash
/opt/miniconda3/envs/py311/bin/pip install -r requirements.txt
```

## 运行

```bash
/opt/miniconda3/envs/py311/bin/python main.py
```

启动后程序会自动拉起 LiteLLM Proxy（默认 `127.0.0.1:4000`）并进入对话。

## 命令行命令

| 命令 | 说明 |
| --- | --- |
| `/model <名称>` | 切换模型（`deepseek` / `gpt` / `claude`） |
| `/reset` | 清空当前对话上下文（保留长期记忆） |
| `/memory` | 查看长期记忆档案 |
| `/help` | 显示帮助 |
| `/exit` | 退出程序 |

默认模型为 `deepseek`。

## 内置工具（Tools Plugin）

通过 Tool Registry 统一管理，调用链为：注册 Schema → schema 生成 → tool_call 解析 → tool 执行。

| 工具 | 功能 |
| --- | --- |
| `bash` | 执行 shell 命令（带超时与输出截断） |
| `read_file` | 读取本地文本文件 |
| `write_file` | 写入本地文本文件 |
| `fetch_url` | 抓取网页正文（requests + BeautifulSoup） |
| `web_search` | 联网搜索（Tavily API） |
| `python_repl` | 子进程执行 Python 代码 |

新增工具：在 `src/tools/` 下新建模块，用 `@registry.register(...)` 装饰执行函数，并在 `src/tools/__init__.py` 中导入即可自动注册。

## 记忆系统

基于 Markdown 文件：

- `memory/user.md`：长期用户美食档案（健康与饮食限制、口味与习惯、家人与场景、厨房设备与预算、其他），启动时注入系统提示；Agent 可借助 `update_user` / `write_file` 更新。
- Web 聊天会话保存在 `memory/users/{uid}/sessions/*.json`，可通过记忆提取 API 更新 user.md。

## 安全提示

`bash` 与 `python_repl` 默认直接在本机执行，仅做超时与输出截断保护，不含沙箱隔离。请在可信环境下使用。
