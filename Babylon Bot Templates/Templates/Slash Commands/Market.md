---
template_id: slash_market
command: /market
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /market

Use for a current market overview. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`market_summary`, `market_metrics`, `market_highlights`, `timestamp_unix`, `data_quality`

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
          "content": "# 📊 /market\nUse for a current market overview."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Market snapshot\n{{market_summary}}"
        },
        {
          "type": 10,
          "content": "### Key metrics\n{{market_metrics}}"
        },
        {
          "type": 10,
          "content": "### Highlights\n{{market_highlights}}"
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
