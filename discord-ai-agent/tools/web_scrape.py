"""
Web scraping tool. Distinct from web_search: this fetches ONE specific URL
the user (or the model) already has, and pulls out clean readable content
plus links — for when you already know where to look, rather than needing
to discover pages via search.

Kept polite by design: identifies itself with a real user agent, checks
robots.txt before fetching, times out quickly, and caps how much content
it pulls back so it doesn't blow the model's context window on one page.
"""
import asyncio
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; DiscordAIAgent/1.0; +https://github.com/)"
MAX_CHARS = 6000
MAX_LINKS = 25
TIMEOUT_SECONDS = 15


async def _robots_allows(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)

    def _read():
        try:
            rp.read()
        except Exception:
            # If robots.txt is unreachable/malformed, default to allowing —
            # matches how most browsers and crawlers behave.
            return True
        return True

    await asyncio.to_thread(_read)
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


async def scrape_url(url: str, extract: str = "text") -> str:
    """
    extract: "text" for readable page content, "links" for the page's
    outbound links (useful for the agent to decide where to look next).
    """
    if not url.startswith(("http://", "https://")):
        return f"Invalid URL: {url}"

    if not await _robots_allows(url):
        return f"robots.txt on this site disallows scraping {url}; skipping."

    headers = {"User-Agent": USER_AGENT}
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return f"Failed to fetch {url}: HTTP {resp.status}"
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" not in content_type and "application/xhtml" not in content_type:
                    return f"URL did not return HTML content (Content-Type: {content_type})."
                html = await resp.text(errors="ignore")
    except asyncio.TimeoutError:
        return f"Timed out fetching {url}."
    except Exception as e:
        return f"Error fetching {url}: {e}"

    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()

    if extract == "links":
        links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            if href not in seen and href.startswith(("http://", "https://")):
                seen.add(href)
                text = a.get_text(strip=True)[:80]
                links.append(f"{text or '(no text)'} -> {href}")
            if len(links) >= MAX_LINKS:
                break
        return "\n".join(links) if links else "No links found on this page."

    title = soup.title.get_text(strip=True) if soup.title else ""
    body_text = soup.get_text(separator="\n", strip=True)
    lines = [l for l in body_text.splitlines() if l.strip()]
    cleaned = "\n".join(lines)

    if len(cleaned) > MAX_CHARS:
        cleaned = cleaned[:MAX_CHARS] + "\n...[truncated]"

    header = f"Title: {title}\nURL: {url}\n\n" if title else f"URL: {url}\n\n"
    return header + cleaned


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "scrape_url",
        "description": (
            "Fetch a specific, known URL and extract its readable content or "
            "outbound links. Use this when you already have a URL (from the "
            "user or from a prior web_search result) and need the actual page "
            "content — web_search only gives short snippets, not full pages. "
            "Respects robots.txt and only reads publicly accessible pages."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The exact URL to fetch, including http(s)://",
                },
                "extract": {
                    "type": "string",
                    "enum": ["text", "links"],
                    "description": "\"text\" for readable page content (default), \"links\" for outbound links.",
                },
            },
            "required": ["url"],
        },
    },
}
