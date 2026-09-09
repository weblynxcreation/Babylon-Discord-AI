---
template_id: slash_command_settings
channel: interaction-response
status: draft
tags:
  - template
  - slash-command
  - settings
  - components-v2
---

# Settings Summary

Use for read-only configuration commands such as `/automod settings` and `/raid config`. Populate only settings returned by the server configuration.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
  "components": [
    {
      "type": 17,
      "accent_color": 3447003,
      "components": [
        {"type": 10, "content": "# ⚙️ {{settings_title}}\nCurrent server configuration."},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "### Active settings\n{{settings_details}}"},
        {"type": 10, "content": "{{help_text}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "-# Retrieved <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R>"},
        {"type": 10, "content": "{{data_quality}}"}
      ]
    }
  ]
}
```
