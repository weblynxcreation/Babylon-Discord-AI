import unittest
from response_cards import _production_text, build_production_view

class ProductionTextTests(unittest.TestCase):
    def test_markdown_table_is_compacted_for_code_block(self):
        body = """**How to build**\n| Step | Wiki | Source |\n|---|---|---|\n| 1 | **Build a factory** | [source-1†L1-L12] |\n&nbsp;&nbsp; CPU - [wiki](https://example.test/cpu)\n```"""
        result = _production_text(body)
        self.assertNotIn("|", result)
        self.assertNotIn("**", result)
        self.assertNotIn("source-1", result)
        self.assertIn("Step · Wiki · Source", result)
        self.assertIn("Build a factory", result)

    def test_factory_parcel_claim_is_removed_and_marked_unverified(self):
        result = _production_text("1. Build a factory parcel - the only parcel that can hold production machines.")
        self.assertNotIn("Build a factory parcel", result)
        self.assertEqual(result, "Some machine types require indoor spaces.")


class FactoryGroundingTests(unittest.IsolatedAsyncioTestCase):
    async def test_factory_query_focuses_on_product_name(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        import agent
        wiki = AsyncMock(side_effect=[
            json.dumps({"data": {"results": [{"title": "Computer", "path": "Wiki/Items/Computer.md"}]}}),
            json.dumps({"data": {"name": "Computer", "recipe_machine": "[[Electronics Bench]]"}}),
        ])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="verified", tool_calls=None))])))))
        with patch.object(agent, '_client', client), patch.dict(agent.TOOL_IMPLS, {'capital_rift_wiki': wiki}), patch.dict(__import__('os').environ, {'AGENT_TURN_TIMEOUT_SECONDS':'2'}):
            await agent.run_agent([], 'How do I build a computer factory?')
        self.assertEqual(wiki.await_args_list[0].kwargs['query'], 'computer')
        self.assertEqual(wiki.await_args_list[1].kwargs['note_path'], 'Wiki/Items/Computer.md')


class DeterministicFactoryRoutingTests(unittest.TestCase):
    def test_subject_extraction_removes_request_words(self):
        import bot
        self.assertEqual(bot._factory_subject("How do I make a computer factory?"), "computer")
        self.assertEqual(bot._factory_subject("build a bucket wheel excavator production line"), "bucket wheel excavator")
        self.assertEqual(bot._factory_subject('how do I make a factory capable of 1 computer per minute'), 'computer')
        self.assertEqual(bot._factory_subject('How do I make a factory capable of producing a Bucket Wheel Excavator'), 'Bucket Wheel Excavator')
        self.assertEqual(bot._factory_subject('How do I make a facotry for bucket wheel excavators?'), 'bucket wheel excavator')

    def test_direct_recipe_questions_use_card_routing(self):
        import bot
        self.assertTrue(bot._wants_factory_card('How do I make a glass display counter?'))
        self.assertTrue(bot._wants_factory_card('recipe for Power Supply'))
        self.assertFalse(bot._wants_factory_card('What is the server status?'))
        self.assertTrue(bot._wants_wiki_count('How many items are there in Capital Rift?'))
        self.assertFalse(bot._wants_wiki_count('How do I make a glass display counter?'))
        self.assertTrue(bot._wants_overbroad_request('explain every production chain in the wiki'))
        self.assertFalse(bot._wants_overbroad_request('how do I make a computer?'))

class ProductionLayoutTests(unittest.TestCase):
    def test_layout_and_storage_use_distinct_fields(self):
        import json
        note = {
            "path": "Wiki/Items/Computer.md",
            "title": "Computer",
            "content": """---
name: Computer
source: https://wiki.capitalrift.com/items/computer/
image: https://wiki.capitalrift.com/icons/computer.webp
recipe_name: Assemble a computer
recipe_machine: [[Electronics Bench]]
recipe_input_cost: 3295
recipe_output_quantity: 1
recipe_rate_per_minute: 0.01
placement: Stands on a table-height surface
---
| 1 | [[Motherboard]] |
| 1 | [[CPU]] |
""",
        }
        view = build_production_view("Computer", "", wiki_context=json.dumps({"exact_note": note}))
        text = "\n".join(component["content"] for component in view.to_components()[0]["components"] if component.get("type") == 10)
        self.assertIn("Electronics Bench -> Computer", text)
        self.assertIn("Storage details are not stated in the retrieved wiki.", text)
        self.assertNotIn("Stands on a table-height surface", text)
        self.assertNotIn("[machine] -> [output]", text)

class ProductionCommandTests(unittest.IsolatedAsyncioTestCase):
    def _interaction(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        return SimpleNamespace(
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )

    def _note(self, *, with_rate=True):
        rate = "recipe_rate_per_minute: 2" if with_rate else ""
        return {
            "title": "Iron Plate",
            "path": "Wiki/Items/Iron Plate.md",
            "content": (
                "---\nname: Iron Plate\nsource: https://wiki.capitalrift.com/items/iron-plate/\n"
                f"recipe_machine: [[Furnace]]\nrecipe_output_quantity: 1\n{rate}\n---\n"
                "## Recipe\n#### Ingredients\n| Quantity | Item |\n|---|---|\n| 2 | [[Iron Ore]] |\n"
            ),
        }

    async def test_production_uses_parsed_recipe_for_machine_count(self):
        from unittest.mock import AsyncMock, patch
        import bot
        interaction = self._interaction()
        with patch("bot._capital_rift_note", AsyncMock(return_value=(self._note(), None))):
            await bot.production.callback(interaction, "Iron Plate", 10.0)
        interaction.response.defer.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        view = kwargs["view"]
        body = next(c["content"] for c in view.to_components()[0]["components"] if c.get("type") == 10 and "Machines needed" in c.get("content", ""))
        self.assertIn("5 Furnace", body)
        self.assertIn("10/min", body)

    async def test_production_missing_rate_reports_recipe_issues(self):
        from unittest.mock import AsyncMock, patch
        import bot
        interaction = self._interaction()
        with patch("bot._capital_rift_note", AsyncMock(return_value=(self._note(with_rate=False), None))):
            await bot.production.callback(interaction, "Iron Plate", 10.0)
        kwargs = interaction.followup.send.call_args.kwargs
        self.assertTrue(kwargs.get("ephemeral"))
        self.assertEqual(kwargs["view"].to_components()[0]["accent_color"], 0xE74C3C)

    async def test_production_autocompletes_indexed_titles(self):
        import json
        from unittest.mock import AsyncMock, patch
        import bot
        search = AsyncMock(return_value=json.dumps(
            {"data": {"results": [{"title": "Iron Plate", "path": "a.md"}, {"title": "Iron Ore", "path": "b.md"}]}}
        ))
        with patch("bot.capital_rift_wiki", search):
            choices = await bot.production_item_autocomplete(None, "iron")
        self.assertEqual([choice.value for choice in choices], ["Iron Plate", "Iron Ore"])


class StatusCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_card_is_green_when_everything_is_configured(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        import bot
        config = {
            "setup_complete": True, "admin_role_id": 1, "market_channel_id": 2,
            "mod_log_channel_id": 3,
        }
        interaction = SimpleNamespace(
            guild_id=1,
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        wiki = AsyncMock(return_value=json.dumps({"data": {"totalNotes": 120}}))
        with patch("bot.capital_rift_wiki", wiki), \
             patch.object(bot.market_client, "get_companies", AsyncMock(return_value=[object()] * 4)), \
             patch.object(bot.client, "ws", __import__("types").SimpleNamespace(latency=0.12)), \
             patch.object(bot.mod_store, "get_guild_config", AsyncMock(return_value=config)), \
             patch.dict(__import__('os').environ, {"NVIDIA_API_KEY": "k", "TAVILY_API_KEY": "k"}, clear=False):
            await bot.status.callback(interaction)
        kwargs = interaction.followup.send.call_args.kwargs
        self.assertEqual(kwargs["view"].to_components()[0]["accent_color"], 0x2ECC71)
        self.assertTrue(kwargs.get("ephemeral"))

    async def test_status_card_flags_market_and_setup_warnings(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        import bot
        from babylon_market import BabylonAPIError
        interaction = SimpleNamespace(
            guild_id=1,
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        wiki = AsyncMock(return_value=json.dumps({"data": {"totalNotes": 120}}))
        with patch("bot.capital_rift_wiki", wiki), \
             patch.object(bot.market_client, "get_companies", AsyncMock(side_effect=BabylonAPIError("offline"))), \
             patch.object(bot.client, "ws", __import__("types").SimpleNamespace(latency=0.12)), \
             patch.object(bot.mod_store, "get_guild_config", AsyncMock(return_value={})), \
             patch.dict(__import__('os').environ, {"NVIDIA_API_KEY": "k"}, clear=False):
            await bot.status.callback(interaction)
        kwargs = interaction.followup.send.call_args.kwargs
        self.assertEqual(kwargs["view"].to_components()[0]["accent_color"], 0xE67E22)
