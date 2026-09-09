---
template_id: slash_market_status
command: /market-status
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /market-status

Use for market verification and synchronization health. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`sync_status`, `last_sync`, `status_details`, `timestamp_unix`, `data_quality`

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
          "content": "# 🩺 /market-status\nUse for market verification and synchronization health."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Status\n{{sync_status}}"
        },
        {
          "type": 10,
          "content": "### Last synchronization\n{{last_sync}}"
        },
        {
          "type": 10,
          "content": "### Issues\n{{status_details}}"
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
