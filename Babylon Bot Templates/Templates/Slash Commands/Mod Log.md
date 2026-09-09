---
template_id: slash_modlog
command: /modlog
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /modlog

Use after the moderation-log channel is set. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`channel_mention`, `moderator_mention`, `result_details`, `timestamp_unix`, `data_quality`

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
          "content": "# 📋 /modlog\nUse after the moderation-log channel is set."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Moderation-log channel\n{{channel_mention}}"
        },
        {
          "type": 10,
          "content": "### Changed by\n{{moderator_mention}}"
        },
        {
          "type": 10,
          "content": "### Result\n{{result_details}}"
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
