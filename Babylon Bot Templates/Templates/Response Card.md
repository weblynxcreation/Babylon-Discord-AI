---
template_id: response_card
status: ready
tags: [template, components-v2]
---

# Response Card

Shared runtime card for AI answers, wiki notes, and errors. Body and footer are
supplied by the bot; the template makes no claims about source verification.
Attachments are added by the runtime as Media Gallery or File components.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
  "components": [
    {
      "type": 17,
      "accent_color": "{{accent_color}}",
      "components": [
        {"type": 10, "content": "## {{title}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "{{body}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "-# {{footer}}"}
      ]
    }
  ]
}
```
