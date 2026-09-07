---
template_id: slash_purge
command: /purge
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /purge

Use after messages are purged from a channel. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`channel_mention`, `message_count`, `moderator_mention`, `timestamp_unix`, `data_quality`

```json
{
  "flags": 32768,
  "allowed_mentions": {
    "parse": []
  },
  "components": [
    {
      "type": 17,
      "accent_color": 16705372,
      "components": [
        {
          "type": 10,
          "content": "# 🧹 /purge\nUse after messages are purged from a channel."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Channel\n{{channel_mention}}"
        },
        {
          "type": 10,
          "content": "### Messages removed\n{{message_count}}"
        },
        {
          "type": 10,
          "content": "### Moderator\n{{moderator_mention}}"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "-# Generated <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R>"
        },
        {
          "type": 10,
          "content": "{{data_quality}}"
        }
      ]
    }
  ]
}
```
