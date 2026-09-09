# Components V2 foundation

Shared implementation: card_primitives.py, response_cards.py, and
component_templates.py. This is the foundation for issue #7.

## Use the shared sender

Use send_card(send, title, body, state=...) for structured lookup, administrative,
moderation, and generated-media responses. It suppresses mentions, closes file
handles, references attachments through V2 media/file components, and marks
delivery for the response lifecycle. Do not mix content or embeds with a V2 view.

Keep ordinary conversational answers in plain text. Conversational timeouts use
plain text plus the existing Send logs button. A classic View is not placed
inside a LayoutView. Dynamic V2 buttons belong in labeled ActionRows.

## States and appearance

| State | Visible heading | Accent |
| --- | --- | --- |
| info | Supplied title | Gold |
| success | Success | Green |
| warning | Warning | Orange |
| error | Error | Red |
| loading | Working | Gold |
| empty | No results | Gold |

State meaning is conveyed by words as well as color. Existing error=True and
accent arguments remain compatible. Use semantic states for new features.
A loading card is temporary: its owner must replace it in every terminal path.

build_card provides the common title/body/footer layout and optional thumbnail.
Specialized production templates continue to use build_layout_view, which shares
the same validation. Shared tokens define body length and accent colors.
add_actions adds a row of 1–5 buttons; every button needs a readable label.
Dynamic views must disable expired controls and explain how to reopen the result.

## Content and mobile layout

- Keep titles short, labels explicit, and one idea per paragraph.
- Lead with the user-requested result; reveal detailed lists through navigation.
- Keep wiki source URLs clickable and preserve complete link tokens on pagination.
- Long fenced code blocks close and reopen on each page.
- Use image descriptions and readable button labels; do not rely on emoji/color alone.
- Each view stays within 4,000 text characters and 40 components; bodies normally
  stay within 3,000 characters. validate_view also runs after media is attached.
- Never silently truncate a production branch or invent missing wiki values.
  Oversized indivisible links/records fail visibly through the response guard.

The factory overview, input/machine breakdowns, three-stage pages, and notes use
the same primitive. They edit one message through their navigation buttons.
Partial factory plans have a visible warning and a Notes section.

## Tests

The card suites validate standard states, clickable-link boundaries, long code
formatting, image/file references, mention suppression, component/text limits,
navigation, partial data, and expiry. Tests use Discord component serialization,
so they do not require sending messages to a real server.
