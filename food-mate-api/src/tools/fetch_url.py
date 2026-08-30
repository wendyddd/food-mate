"""
fetch_url tool: fetch a page with requests and extract body text via beautifulsoup4.
"""

import requests
from bs4 import BeautifulSoup

from src.tools.registry import registry

# Request timeout (seconds)
FETCH_TIMEOUT = 20
# Max body characters
MAX_CONTENT_CHARS = 10000
# Mimic a browser UA to reduce blocking
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
    Fetch a web page and extract body text.

    Args:
        url (str): page URL

    Returns:
        str: extracted page text, or an error message on failure
    """
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        return f"[fetch_url 失败] {url}: {e}"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove scripts, styles, and other non-content tags
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    # Extract title and body text
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    text = soup.get_text(separator="\n", strip=True)

    # Collapse extra blank lines
    lines = [line for line in text.splitlines() if line.strip()]
    content = "\n".join(lines)

    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "\n...[truncated — content too long]"

    return f"Title: {title}\nSource: {url}\n\n{content}"
