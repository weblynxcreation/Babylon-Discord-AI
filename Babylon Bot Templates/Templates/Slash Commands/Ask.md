---
template_id: slash_ask
command: /ask
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /ask

Use for a source-backed AI answer. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`answer`, `sources`, `answer_limits`, `timestamp_unix`, `data_quality`

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
          "content": "# 🤖 /ask\nUse for a source-backed AI answer."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Answer\n{{answer}}"
        },
        {
          "type": 10,
          "content": "### Sources\n{{sources}}"
        },
        {
          "type": 10,
          "content": "### Limits\n{{answer_limits}}"
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
