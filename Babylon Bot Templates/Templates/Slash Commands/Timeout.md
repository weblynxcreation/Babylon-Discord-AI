---
template_id: slash_timeout
command: /timeout
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /timeout

Use after a member receives a timeout. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`target_mention`, `moderator_mention`, `duration`, `reason`, `timestamp_unix`, `data_quality`

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
          "content": "# ⏱️ /timeout\nUse after a member receives a timeout."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Member\n{{target_mention}}"
        },
        {
          "type": 10,
          "content": "### Moderator\n{{moderator_mention}}"
        },
        {
          "type": 10,
          "content": "### Duration\n{{duration}}"
        },
        {
          "type": 10,
          "content": "### Reason\n{{reason}}"
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
