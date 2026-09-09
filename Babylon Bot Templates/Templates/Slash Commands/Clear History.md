---
template_id: slash_clearhistory
command: /clearhistory
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /clearhistory

Use after conversation memory is cleared. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`cleared_scope`, `result_details`, `next_step`, `timestamp_unix`, `data_quality`

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
          "content": "# 🧹 /clearhistory\nUse after conversation memory is cleared."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Cleared scope\n{{cleared_scope}}"
        },
        {
          "type": 10,
          "content": "### Result\n{{result_details}}"
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
