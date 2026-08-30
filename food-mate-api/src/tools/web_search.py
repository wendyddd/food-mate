"""
web_search tool: call the Tavily search API and return results related to the query.
"""

import os

import requests

from src.tools.registry import registry

# Tavily search endpoint
TAVILY_ENDPOINT = "https://api.tavily.com/search"
# Request timeout (seconds)
SEARCH_TIMEOUT = 20
# Default number of results
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
    Search the web via the Tavily API.

    Args:
        query (str): search keywords or question
        max_results (int): number of results to return, default 5

    Returns:
        str: formatted results (title + snippet + link), or an error message on failure
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

    # Assemble a readable search-result text
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
