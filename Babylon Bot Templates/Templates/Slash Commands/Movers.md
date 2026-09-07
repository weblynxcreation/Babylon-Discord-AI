---
template_id: slash_movers
command: /movers
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /movers

Use for verified market gainers and losses. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`market_window`, `gainers`, `losers`, `timestamp_unix`, `data_quality`

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
          "content": "# 📈 /movers\nUse for verified market gainers and losses."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Time window\n{{market_window}}"
        },
        {
          "type": 10,
          "content": "### Gainers\n{{gainers}}"
        },
        {
          "type": 10,
          "content": "### Losses\n{{losers}}"
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
