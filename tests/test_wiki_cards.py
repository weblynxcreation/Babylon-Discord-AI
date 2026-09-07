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
