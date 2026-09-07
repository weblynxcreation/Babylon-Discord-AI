import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import agent
from tools import capital_rift


class _FakeCompletions:
    def __init__(self):
        self.calls = []
        self.received_wiki_result = False

    def create(self, **kwargs):
        self.calls.append(kwargs)
        messages = kwargs["messages"]

        if len(self.calls) == 1:
            tool_names = {
                tool["function"]["name"]
                for tool in kwargs.get("tools", [])
            }
            if "capital_rift_wiki" not in tool_names:
                raise AssertionError("The Obsidian wiki tool was not offered to the agent.")

            tool_call = SimpleNamespace(
                id="wiki-call-1",
                function=SimpleNamespace(
                    name="capital_rift_wiki",
                    arguments=json.dumps(
                        {
                            "action": "search",
                            "query": "quantum widget crystals",
                            "limit": 3,
                        }
                    ),
                ),
            )
            message = SimpleNamespace(content="", tool_calls=[tool_call])
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        tool_messages = [item for item in messages if item.get("role") == "tool"]
        if not tool_messages:
            raise AssertionError("The Obsidian tool result never reached the agent.")

        tool_content = tool_messages[-1]["content"]
        self.received_wiki_result = (
            "Recipes/Quantum Widget.md" in tool_content
            and "7 luminous crystals" in tool_content
            and "Local Capital Rift Obsidian vault" in tool_content
        )
        if not self.received_wiki_result:
            raise AssertionError(f"Unexpected wiki result: {tool_content}")

        message = SimpleNamespace(
            content=(
                "According to Recipes/Quantum Widget.md, "
                "a Quantum Widget requires 7 luminous crystals."
            ),
            tool_calls=None,
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeClient:
    def __init__(self):
        self.completions = _FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


class AgentObsidianIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_receives_real_obsidian_search_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault = root / "Capital Rift Wiki"
            recipe_dir = vault / "Recipes"
            recipe_dir.mkdir(parents=True)
            (recipe_dir / "Quantum Widget.md").write_text(
                "# Quantum Widget\n\n"
                "A Quantum Widget requires 7 luminous crystals per cycle.\n",
                encoding="utf-8",
            )

            fake_client = _FakeClient()
            environment = {
                "CAPITAL_RIFT_VAULT_PATH": str(vault),
                "CAPITAL_RIFT_INDEX_PATH": str(root / "index" / "wiki.db"),
                "CAPITAL_RIFT_VAULT_REFRESH_SECONDS": "0",
            }

            capital_rift._WIKI_INDEX = None
            try:
                with patch.dict(os.environ, environment, clear=False), patch.object(
                    agent, "_client", fake_client
                ):
                    result = await agent.run_agent(
                        [],
                        "How many luminous crystals does a Quantum Widget require?",
                    )
            finally:
                capital_rift._WIKI_INDEX = None

            self.assertTrue(fake_client.completions.received_wiki_result)
            self.assertIn("7 luminous crystals", result.text)
            self.assertIn("Recipes/Quantum Widget.md", result.text)


if __name__ == "__main__":
    unittest.main()
