"""Shared Components V2 states, pagination, validation, and action rows."""
import re
import discord

GOLD = 0xD4AF37
ERROR = 0xE74C3C
GREEN = 0x2ECC71
ORANGE = 0xE67E22
BODY_LIMIT = 3000
STATES = {
    "info": ("", GOLD), "success": ("Success", GREEN),
    "warning": ("Warning", ORANGE), "error": ("Error", ERROR),
    "loading": ("Working", GOLD), "empty": ("No results", GOLD),
}


class CardError(ValueError):
    pass


def paginate_text(text, limit=BODY_LIMIT):
    """Keep wiki links intact and reopen long fenced code blocks on each page."""
    tokens = re.findall(r"```[^\n]*\n[\s\S]*?```|\[[^\]\n]+\]\([^\n)]+\)|[^\s]+|\s+", text)
    pages, current = [], ""
    for token in tokens:
        if len(token) > limit and token.startswith("```"):
            opening, body = token.split("\n", 1)
            body = body[:-3]
            room = limit - len(opening) - 5
            if room < 1:
                raise CardError("Code block language label is too long.")
            if current:
                pages.append(current)
                current = ""
            for start in range(0, len(body), room):
                pages.append(opening + "\n" + body[start:start + room] + "\n```")
            continue
        if len(token) > limit and re.fullmatch(r"\[[^\]\n]+\]\([^\n)]+\)", token):
            raise CardError("A source link is too long for a Discord card.")
        while token:
            if len(current) + len(token) <= limit:
                current += token
                break
            if current:
                pages.append(current)
                current = ""
            if len(token) <= limit:
                current = token
                break
            pages.append(token[:limit])
            token = token[limit:]
    if current:
        pages.append(current)
    return pages or ["No results found."]


def validate_view(view):
    if view.content_length() > 4000 or view.total_children_count > 40:
        raise CardError("Card exceeds Discord's display/component budget.")
    return view


def build_card(title, body, *, footer="Babylon Helper", state="info", accent=None, thumbnail=None):
    from component_templates import build_layout_view
    if state not in STATES:
        raise CardError(f"Unknown card state: {state}")
    label, color = STATES[state]
    heading = f"{label} · {title}" if label else str(title)
    view = build_layout_view("wiki_response_card" if thumbnail else "response_card", {
        "title": heading[:200], "body": body if str(body).strip() else "\u200b" + str(body),
        "footer": str(footer)[:350], "accent_color": color if accent is None else accent,
        "thumbnail": thumbnail,
    })
    return validate_view(view)


def add_actions(view, *buttons):
    if not 1 <= len(buttons) <= 5:
        raise CardError("An action row needs 1–5 labeled buttons.")
    if any(not button.label for button in buttons):
        raise CardError("Every action needs a readable label.")
    row = discord.ui.ActionRow(*buttons)
    view.add_item(row)
    return validate_view(view)
