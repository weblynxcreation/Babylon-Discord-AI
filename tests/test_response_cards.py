import io
import unittest
from unittest.mock import AsyncMock

import discord

from response_cards import build_response_views, send_card


class ResponseCardTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_answer_preserved_and_each_page_within_discord_limits(self):
        body = 'Verified wiki content.\n' * 400
        views = build_response_views('Answer', body)
        recovered = ''
        for view in views:
            self.assertTrue(view.has_components_v2())
            self.assertLessEqual(view.content_length(), 4000)
            self.assertLessEqual(view.total_children_count, 40)
            recovered += view.to_components()[0]['components'][2]['content']
        self.assertEqual(recovered, body)
        self.assertGreater(len(views), 1)

    async def test_send_uses_components_only_and_suppresses_mentions(self):
        send = AsyncMock()
        await send_card(send, 'Answer', '@everyone <@123>')
        kwargs = send.call_args.kwargs
        self.assertNotIn('content', kwargs)
        self.assertNotIn('embed', kwargs)
        self.assertEqual(kwargs['allowed_mentions'].to_dict()['parse'], [])
        self.assertTrue(kwargs['view'].has_components_v2())

    async def test_attachments_referenced_and_sent_only_once(self):
        send = AsyncMock()
        files = [discord.File(io.BytesIO(b'png'), filename='generated.png'),
                 discord.File(io.BytesIO(b'zip'), filename='project.zip')]
        await send_card(send, 'Generated files', 'x' * 7000, files=files)
        first = send.call_args_list[0].kwargs
        payload = first['view'].to_components()
        self.assertEqual(payload[1]['type'], 12)
        self.assertEqual(payload[1]['items'][0]['media']['url'], 'attachment://generated.png')
        self.assertEqual(payload[2]['type'], 13)
        self.assertEqual(payload[2]['file']['url'], 'attachment://project.zip')
        self.assertEqual(first['files'], files)
        for later in send.call_args_list[1:]:
            self.assertNotIn('files', later.kwargs)

    async def test_error_and_ephemeral_delivery(self):
        send = AsyncMock()
        await send_card(send, 'Wiki unavailable', 'Missing wiki', error=True, ephemeral=True)
        kwargs = send.call_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertEqual(kwargs['view'].to_components()[0]['accent_color'], 0xE74C3C)
