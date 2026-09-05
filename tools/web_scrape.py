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
import ipaddress
import socket
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; DiscordAIAgent/1.0; +https://github.com/)"
MAX_CHARS = 6000
MAX_LINKS = 25
TIMEOUT_SECONDS = 15


def _is_safe_public_ip(ip_str: str) -> bool:
    """Rejects loopback/private/link-local/multicast/reserved addresses,
    including the AWS/GCP/Azure metadata address (169.254.169.254 falls
    under link-local). This tool takes URLs from the LLM, which can be
    steered by content it previously read (prompt injection), so it must
    not be usable to reach internal network services or cloud metadata."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _resolves_to_public_address(url: str) -> bool:
    hostname = urlparse(url).hostname
    if not hostname:
        return False

    def _resolve():
        try:
            return {info[4][0] for info in socket.getaddrinfo(hostname, None)}
        except socket.gaierror:
            return set()

    addresses = await asyncio.to_thread(_resolve)
    if not addresses:
        return False
    # Every resolved address must be public — if a hostname resolves to
    # both a public and a private address, treat it as unsafe rather than
    # racing DNS (a classic DNS-rebinding SSRF pattern).
    return all(_is_safe_public_ip(addr) for addr in addresses)


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

    if not await _resolves_to_public_address(url):
        return f"Refusing to fetch {url}: it does not resolve to a public address."

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
