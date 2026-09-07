---
template_id: slash_image
command: /image
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /image

Use after an image-generation request completes. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`prompt`, `result_url`, `generation_notes`, `timestamp_unix`, `data_quality`

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
          "content": "# 🖼️ /image\nUse after an image-generation request completes."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Prompt\n{{prompt}}"
        },
        {
          "type": 10,
          "content": "### Result\n[Open result]({{result_url}})"
        },
        {
          "type": 10,
          "content": "### Notes\n{{generation_notes}}"
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
