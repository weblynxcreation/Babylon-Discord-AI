---
template_id: slash_command_error
channel: interaction-response
status: draft
tags:
  - template
  - slash-command
  - error
  - components-v2
---

# Command Error

Use when a slash command cannot complete because of validation, missing permission, unavailable source data, or a failed bot action. State the actual failure; never substitute an assumed value.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
  "components": [
    {
      "type": 17,
      "accent_color": 15158332,
      "components": [
        {"type": 10, "content": "# ⚠️ {{error_title}}\n**/{{command_name}}** could not complete."},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "### What happened\n{{error_details}}"},
        {"type": 10, "content": "### How to continue\n{{resolution}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "-# Reported <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R>"},
        {"type": 10, "content": "{{data_quality}}"}
      ]
    }
  ]
}
```
