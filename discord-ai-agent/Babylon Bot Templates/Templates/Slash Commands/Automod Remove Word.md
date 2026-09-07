---
template_id: slash_automod_removeword
command: /automod removeword
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /automod removeword

Use after a banned word or phrase is removed. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`rule_value`, `moderator_mention`, `list_status`, `timestamp_unix`, `data_quality`

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
          "content": "# ➖ /automod removeword\nUse after a banned word or phrase is removed."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Removed rule\n{{rule_value}}"
        },
        {
          "type": 10,
          "content": "### Changed by\n{{moderator_mention}}"
        },
        {
          "type": 10,
          "content": "### Current list status\n{{list_status}}"
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
