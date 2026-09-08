import unittest
from wiki_cards import format_wiki_note
from response_cards import build_response_views


class WikiCardTests(unittest.IsolatedAsyncioTestCase):
    async def test_imported_note_becomes_readable_card(self):
        note = {'content': '''---
name: "Computer"
image: "https://wiki.capitalrift.com/icons/computer.webp"
source: "https://wiki.capitalrift.com/items/computer/"
stack_size: 99
---
<!-- GENERATED: importer -->
# Computer
![Computer](https://wiki.capitalrift.com/icons/computer.webp)
Description.
## Recipe
| Machine | Rate |
|---|---:|
| [[Electronics Bench]] | 0.01/min |
#### Ingredients
| Quantity | Item | Base cost |
|---:|---|---:|
| 2 | [[RAM Stick]] | $160 |
## Source
Internal source block
'''}
        card = format_wiki_note(note)
        self.assertIn('**2 × RAM Stick**', card['body'])
        self.assertIn('**Machine:** Electronics Bench', card['body'])
        self.assertIn('0.01/min', card['body'])
        for unwanted in ('GENERATED', 'stack_size:', '[[', '|---', '![', 'Internal source block'):
            self.assertNotIn(unwanted, card['body'])
        views = build_response_views('Computer', **card)
        self.assertLessEqual(views[0].content_length(), 4000)
        header = views[0].to_components()[0]['components'][0]
        self.assertEqual(header['accessory']['media']['url'], note['content'].split('image: "')[1].split('"')[0])

    async def test_missing_metadata_and_unusable_image(self):
        card = format_wiki_note({'path': 'Guide.md', 'content': '# Guide\nPlain [[Iron Bar|iron]] guide.'})
        self.assertIsNone(card['thumbnail'])
        self.assertEqual(card['body'], 'Plain iron guide.')
        self.assertIn('Guide.md', card['footer'])
        self.assertIsNone(format_wiki_note({'content': '---\nimage: "file:///private"\n---\nText'})['thumbnail'])


class WikiLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_note_source_used_and_missing_target_stays_plain(self):
        import json
        from unittest.mock import AsyncMock, patch
        from wiki_cards import linked_wiki_card
        async def lookup(action, **kwargs):
            if action == "read" and kwargs.get("note_path") == "Wiki/Items/Iron Ore.md":
                return json.dumps({"data": {"content": '---\nsource: "https://wiki.capitalrift.com/items/actual-ore-page/"\n---\nOre'}})
            return json.dumps({"data": {"error": "Not found"}})
        note = {"path": "Wiki/Items/Iron Bar.md", "content": "# Iron Bar\nUses [[Iron Ore]] and [[Missing Item]]."}
        with patch("tools.capital_rift.capital_rift_wiki", AsyncMock(side_effect=lookup)):
            card = await linked_wiki_card(note)
        self.assertIn("[Iron Ore](https://wiki.capitalrift.com/items/actual-ore-page/)", card["body"])
        self.assertIn("Missing Item", card["body"])
        self.assertNotIn("[Missing Item]", card["body"])

    async def test_alias_and_anchor_link_to_declared_page(self):
        from wiki_cards import wiki_text
        text = wiki_text("[[Nails#Recipe|Press nails]]", {"Nails": "https://wiki.capitalrift.com/items/nails/"})
        self.assertEqual(text, "[Press nails](https://wiki.capitalrift.com/items/nails/)")
