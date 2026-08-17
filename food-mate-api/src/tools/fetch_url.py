"""
fetch_url 工具，使用 requests 抓取网页并通过 beautifulsoup4 提取正文文本。
"""

import requests
from bs4 import BeautifulSoup

from src.tools.registry import registry

# 请求超时时间（秒）
FETCH_TIMEOUT = 20
# 正文最大字符数
MAX_CONTENT_CHARS = 10000
# 模拟浏览器 UA，降低被拦截概率
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


@registry.register(
    name="fetch_url",
    description="Fetch a URL and return the page body as plain text. Use for articles and reference lookups.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL to fetch (http/https)",
            }
        },
        "required": ["url"],
    },
)
def fetch_url(url: str) -> str:
    """
    抓取网页并提取正文文本

    参数:
        url (str): 网页 URL

    返回:
        str: 提取出的网页正文文本，失败时返回错误提示
    """
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        return f"[fetch_url 失败] {url}: {e}"

    soup = BeautifulSoup(resp.text, "html.parser")

    # 移除脚本、样式等无关标签
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    # 提取标题与正文文本
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    text = soup.get_text(separator="\n", strip=True)

    # 压缩多余空行
    lines = [line for line in text.splitlines() if line.strip()]
    content = "\n".join(lines)

    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "\n...[truncated — content too long]"

    return f"Title: {title}\nSource: {url}\n\n{content}"
