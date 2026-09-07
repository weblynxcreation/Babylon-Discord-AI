"""Shared Components V2 delivery for channels and interaction follow-ups."""
from time import time

import discord

from component_templates import build_layout_view

GOLD = 0xD4AF37
ERROR = 0xE74C3C
GREEN = 0x2ECC71
ORANGE = 0xE67E22
BODY_LIMIT = 3000


def build_response_views(title, body, *, footer=None, error=False, accent=None, files=(), thumbnail=None):
    body = body or 'Done.'
    if error:
        accent = ERROR
    elif accent is None:
        accent = GOLD
    # Preserve the entire response. Each page leaves room for title and footer
    # below Discord's 4,000 aggregate display-character budget.
    chunks = [body[i:i + BODY_LIMIT] for i in range(0, len(body), BODY_LIMIT)]
    views = []
    for index, chunk in enumerate(chunks):
        page = f' · {index + 1}/{len(chunks)}' if len(chunks) > 1 else ''
        view = build_layout_view('wiki_response_card' if thumbnail else 'response_card', {
            'thumbnail': thumbnail,
            'title': str(title)[:180] + page,
            'body': chunk if chunk.strip() else '\u200b' + chunk,
            'footer': str(footer or f'Babylon Helper · <t:{int(time())}:t>')[:350],
            'accent_color': accent,
        })
        if index == 0:
            for file in files:
                uri = f'attachment://{file.filename}'
                if file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                    view.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(
                        uri, description=file.filename,
                    )))
                else:
                    view.add_item(discord.ui.File(uri))
        views.append(view)
    return views


async def send_card(send, title, body, *, footer=None, error=False, accent=None, files=(), ephemeral=None, thumbnail=None):
    """Send only V2 components and explicitly referenced attachments, never embeds/content."""
    files = list(files)
    try:
        views = build_response_views(title, body, footer=footer, error=error, accent=accent, files=files, thumbnail=thumbnail)
        for index, view in enumerate(views):
            kwargs = {'view': view, 'allowed_mentions': discord.AllowedMentions.none()}
            if index == 0 and files:
                kwargs['files'] = files
            if ephemeral is not None:
                kwargs['ephemeral'] = ephemeral
            await send(**kwargs)
    finally:
        for file in files:
            file.close()
