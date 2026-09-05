---
template_id: moderation_permission_error
channel: mod-log
status: draft
tags:
  - template
  - moderation
  - error
  - permissions
  - components-v2
---

# Permission Error

Use when automod or raid protection could not delete, timeout, kick, or ban because the bot lacks a required permission.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
  "components": [
    {
      "type": 17,
      "accent_color": "{{accent_color}}",
      "components": [
        {"type": 10, "content": "# ⚠️ Moderation Action Failed\n**{{intended_action}}** · Case {{case_id}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "### Failure Details\n- **Target:** {{target_mention}}\n- **Source:** {{source_system}}\n- **Required permission:** {{required_permission}}\n- **Channel:** {{channel_mention}}"},
        {"type": 10, "content": "### Reason\n{{reason}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "-# Logged <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R> · Case {{case_id}}"},
        {"type": 10, "content": "{{data_quality}}"}
      ]
    }
  ]
}
```
