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