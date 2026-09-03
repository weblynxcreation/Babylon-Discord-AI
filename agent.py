"""
Agent core: wraps NVIDIA NIM's OpenAI-compatible chat endpoint with a
tool-calling loop. This is the "brain" — it decides when to search the
web, generate an image, or emit code files, then keeps looping until it
has a final text answer.
"""
import os
import json
import asyncio
from openai import OpenAI

from tools.web_search import web_search, TOOL_SCHEMA as WEB_SEARCH_SCHEMA
from tools.web_scrape import scrape_url, TOOL_SCHEMA as WEB_SCRAPE_SCHEMA
from tools.image_gen import generate_image, TOOL_SCHEMA as IMAGE_GEN_SCHEMA
from tools.gif_gen import generate_gif, TOOL_SCHEMA as GIF_GEN_SCHEMA
from tools.codegen import package_files, TOOL_SCHEMA as CODEGEN_SCHEMA
from tools.obsidian import obsidian_search, obsidian_read, TOOL_SCHEMA as OBSIDIAN_SEARCH_SCHEMA, TOOL_SCHEMA_READ as OBSIDIAN_READ_SCHEMA

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

SYSTEM_PROMPT = """You are a helpful, capable AI assistant living in a Discord server.
You can:
- Search the live internet for current information (web_search)
- Fetch and read a specific URL's full content or links (scrape_url)
- Generate images from text descriptions (generate_image)
- Generate short looping animated GIFs from text descriptions (generate_gif)
- Write code or full websites and package them as a downloadable zip (package_files)
- Search a local Obsidian vault for notes and information (obsidian_search)
- Read specific notes from the Obsidian vault (obsidian_read)

Rules:
- Use obsidian_search first when questions are about personal knowledge, gaming strategy, worldbuilding, 
  or other topics likely to be in a local knowledge base. This is faster and more reliable than web search 
  for specific personal/game knowledge.
- Use web_search for current events, facts you're not certain about, or information not in the vault.
- Use scrape_url when you already have a specific URL (from the user, or from a web_search result you want 
  to read in full) — web_search only returns short snippets, scrape_url gets you the actual page content.
- When asked to build something (a website, script, app, bot, etc.), write complete, working file contents 
  yourself, then call package_files with those files. Do not describe code you haven't actually written in full.
- Keep replies concise and conversational — this is a chat interface, not a report.
  Use Discord markdown (code blocks, bold, bullets) where it helps.
- If a request is ambiguous, make a reasonable assumption and say what you assumed rather than stalling 
  with clarifying questions.
"""

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            raise RuntimeError("NVIDIA_API_KEY is not set in the environment.")
        _client = OpenAI(base_url=NIM_BASE_URL, api_key=api_key)
    return _client


TOOLS = [WEB_SEARCH_SCHEMA, WEB_SCRAPE_SCHEMA, IMAGE_GEN_SCHEMA, GIF_GEN_SCHEMA, CODEGEN_SCHEMA, OBSIDIAN_SEARCH_SCHEMA, OBSIDIAN_READ_SCHEMA]

TOOL_IMPLS = {
    "web_search": web_search,
    "scrape_url": scrape_url,
    "generate_image": generate_image,
    "generate_gif": generate_gif,
    "package_files": package_files,
    "obsidian_search": obsidian_search,
    "obsidian_read": obsidian_read,
}


class AgentResult:
    """Holds whatever side-effects a turn produced, alongside the final text."""

    def __init__(self):
        self.text = ""
        self.image_bytes: bytes | None = None
        self.gif_bytes: bytes | None = None
        self.zip_path: str | None = None


async def run_agent(history: list[dict], user_message: str, max_tool_rounds: int = 4) -> AgentResult:
    """
    history: list of {"role": "user"|"assistant", "content": str} from prior turns
    user_message: the new incoming message
    """
    client = _get_client()
    model = os.environ.get("NVIDIA_CHAT_MODEL", "meta/llama-3.1-70b-instruct")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    result = AgentResult()

    for _ in range(max_tool_rounds):
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=2048,
        )
        choice = response.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            result.text = msg.content or ""
            return result

        # Model wants to call one or more tools. Append its request, then
        # append each tool's result, then loop back for a follow-up response.
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            try:
                impl = TOOL_IMPLS[name]
                output = await impl(**args)
            except Exception as e:
                output = f"Tool '{name}' failed: {e}"

            # Capture side-effects the bot layer needs (image bytes / zip path)
            # separately from what goes back to the model as text.
            if name == "generate_image" and isinstance(output, (bytes, bytearray)):
                result.image_bytes = bytes(output)
                tool_text = "Image generated successfully and will be shown to the user."
            elif name == "generate_gif" and isinstance(output, (bytes, bytearray)):
                result.gif_bytes = bytes(output)
                tool_text = "GIF generated successfully and will be shown to the user."
            elif name == "package_files" and isinstance(output, str):
                result.zip_path = output
                tool_text = f"Files packaged successfully at {output}."
            else:
                tool_text = str(output)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_text,
                }
            )

    # Ran out of tool rounds — ask for a final answer with no more tool use.
    final = await asyncio.to_thread(
        client.chat.completions.create,
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=1024,
    )
    result.text = final.choices[0].message.content or "(No response generated.)"
    return result
