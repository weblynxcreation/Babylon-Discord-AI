---
template_id: slash_warn
command: /warn
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /warn

Use after a member receives a warning. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`target_mention`, `moderator_mention`, `action_details`, `reason`, `timestamp_unix`, `data_quality`

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
          "content": "# ⚠️ /warn\nUse after a member receives a warning."
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
          "content": "### Details\n{{action_details}}"
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
