"""
Live web search tool. Uses Tavily, which is purpose-built for feeding
search results to LLM agents (clean text, no HTML scraping headaches).
"""
import os
from tavily import AsyncTavilyClient
from reliability import timeout_seconds

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY is not set in the environment.")
        _client = AsyncTavilyClient(api_key=api_key)
    return _client


async def web_search(query: str, max_results: int = 5) -> str:
    """Use cancellable async HTTP so a timeout does not leave a search thread running."""
    client = _get_client()
    result = await client.search(
        query=query, max_results=max_results, include_answer=True,
        timeout=timeout_seconds("AGENT_TOOL_TIMEOUT_SECONDS", 45),
    )

    lines = []
    if result.get("answer"):
        lines.append(f"Quick answer: {result['answer']}")
    for i, item in enumerate(result.get("results", []), start=1):
        lines.append(
            f"[{i}] {item.get('title', 'Untitled')}\n"
            f"    URL: {item.get('url')}\n"
            f"    {item.get('content', '')[:400]}"
        )
    if not lines:
        return "No results found."
    return "\n".join(lines)


# Tool schema exposed to the LLM (OpenAI-style function calling, which NIM supports)
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the live internet for current information — news, prices, "
            "facts, docs, anything that may have changed since training. "
            "Always use this instead of guessing when the user asks about "
            "current events, recent releases, or anything time-sensitive."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to fetch (default 5).",
                },
            },
            "required": ["query"],
        },
    },
}
