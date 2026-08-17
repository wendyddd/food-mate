"""
web_search 工具，调用 Tavily 搜索 API 返回与查询相关的网页结果。
"""

import os

import requests

from src.tools.registry import registry

# Tavily 搜索接口地址
TAVILY_ENDPOINT = "https://api.tavily.com/search"
# 请求超时时间（秒）
SEARCH_TIMEOUT = 20
# 默认返回结果数量
DEFAULT_MAX_RESULTS = 5


@registry.register(
    name="web_search",
    description="Search the web via Tavily and return titles, snippets, and links. Good for home recipes, cooking techniques, and ingredient facts.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query or question",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (default 5)",
            },
        },
        "required": ["query"],
    },
)
def web_search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
    """
    调用 Tavily API 进行联网搜索

    参数:
        query (str): 搜索关键词或问题
        max_results (int): 返回结果数量，默认 5

    返回:
        str: 格式化的搜索结果（标题 + 摘要 + 链接），失败时返回错误提示
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "[web_search 失败] 未在 .env 中找到 TAVILY_API_KEY"

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": True,
    }

    try:
        resp = requests.post(TAVILY_ENDPOINT, json=payload, timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"[web_search 失败] {e}"

    # 组装可读的搜索结果文本
    parts: list[str] = []
    answer = data.get("answer")
    if answer:
        parts.append(f"概要回答: {answer}\n")

    results = data.get("results", [])
    if not results:
        return "未检索到相关结果。"

    for idx, item in enumerate(results, start=1):
        title = item.get("title", "无标题")
        url = item.get("url", "")
        content = item.get("content", "").strip()
        parts.append(f"{idx}. {title}\n   {content}\n   链接: {url}")

    return "\n".join(parts)
