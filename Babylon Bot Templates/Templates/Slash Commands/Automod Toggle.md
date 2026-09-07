---
template_id: slash_automod_toggle
command: /automod toggle
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /automod toggle

Use after automod is enabled or disabled. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`automod_status`, `moderator_mention`, `next_step`, `timestamp_unix`, `data_quality`

```json
{
  "flags": 32768,
  "allowed_mentions": {
    "parse": []
  },
  "components": [
    {
      "type": 17,
      "accent_color": 5763719,
      "components": [
        {
          "type": 10,
          "content": "# 🛡️ /automod toggle\nUse after automod is enabled or disabled."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### New status\n{{automod_status}}"
        },
        {
          "type": 10,
          "content": "### Changed by\n{{moderator_mention}}"
        },
        {
          "type": 10,
          "content": "### Next step\n{{next_step}}"
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
