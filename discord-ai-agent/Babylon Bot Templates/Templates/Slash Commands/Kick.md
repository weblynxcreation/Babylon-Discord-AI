---
template_id: slash_kick
command: /kick
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /kick

Use after a member is kicked. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`target_mention`, `moderator_mention`, `reason`, `timestamp_unix`, `data_quality`

```json
{
  "flags": 32768,
  "allowed_mentions": {
    "parse": []
  },
  "components": [
    {
      "type": 17,
      "accent_color": 15158332,
      "components": [
        {
          "type": 10,
          "content": "# 👢 /kick\nUse after a member is kicked."
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
