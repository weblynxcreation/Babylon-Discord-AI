---
template_id: slash_leaders
command: /leaders
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /leaders

Use for a verified market ranking. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`ranking_criterion`, `rankings`, `ranking_notes`, `timestamp_unix`, `data_quality`

```json
{
  "flags": 32768,
  "allowed_mentions": {
    "parse": []
  },
  "components": [
    {
      "type": 17,
      "accent_color": 3447003,
      "components": [
        {
          "type": 10,
          "content": "# 🏆 /leaders\nUse for a verified market ranking."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Ranking basis\n{{ranking_criterion}}"
        },
        {
          "type": 10,
          "content": "### Rankings\n{{rankings}}"
        },
        {
          "type": 10,
          "content": "### Notes\n{{ranking_notes}}"
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
