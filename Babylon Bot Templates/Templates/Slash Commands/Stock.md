---
template_id: slash_stock
command: /stock
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /stock

Use for a verified company lookup. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`company_name`, `company_metrics`, `company_summary`, `timestamp_unix`, `data_quality`

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
          "content": "# 🏢 /stock\nUse for a verified company lookup."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Company\n{{company_name}}"
        },
        {
          "type": 10,
          "content": "### Current metrics\n{{company_metrics}}"
        },
        {
          "type": 10,
          "content": "### Summary\n{{company_summary}}"
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
