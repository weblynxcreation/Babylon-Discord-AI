"""Compatibility tools for generic Obsidian search, backed by the secure vault index."""

import json

from tools.capital_rift import capital_rift_wiki


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "obsidian_search",
        "description": (
            "Search the configured local Obsidian vault. Capital Rift questions "
            "should use capital_rift_wiki instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to find in note titles and Markdown content.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMA_READ = {
    "type": "function",
    "function": {
        "name": "obsidian_read",
        "description": "Read a Markdown note returned by obsidian_search.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Relative note path inside the vault.",
                }
            },
            "required": ["filename"],
            "additionalProperties": False,
        },
    },
}


async def obsidian_search(query: str) -> str:
    """Return the legacy generic-search shape using the hardened shared index."""
    raw = json.loads(
        await capital_rift_wiki(action="search", query=query, limit=10)
    )
    data = raw.get("data", {})
    if "error" in data:
        return json.dumps({"error": data["error"]})

    results = [
        {
            "filename": item["path"],
            "excerpt": item["excerpt"],
        }
        for item in data.get("results", [])
    ]
    return json.dumps(
        {
            "query": query,
            "results": results,
            "count": len(results),
            "source": raw.get("source"),
            "readOnly": raw.get("readOnly", True),
        }
    )


async def obsidian_read(filename: str) -> str:
    """Return note Markdown while enforcing shared traversal and size protections."""
    note_path = filename if filename.lower().endswith(".md") else f"{filename}.md"
    raw = json.loads(
        await capital_rift_wiki(action="read", note_path=note_path)
    )
    data = raw.get("data", {})
    if "error" in data:
        return f"Error: {data['error']}"
    return data.get("content", "")
