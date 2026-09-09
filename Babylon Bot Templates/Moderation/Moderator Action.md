---
template_id: moderation_manual_action
channel: mod-log
status: draft
tags:
  - template
  - moderation
  - moderator-action
  - components-v2
---

# Moderator Action

Use for warnings, manual timeouts, kicks, bans, and purges issued through the moderation commands.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
  "components": [
    {
      "type": 17,
      "accent_color": "{{accent_color}}",
      "components": [
        {"type": 10, "content": "# {{action_emoji}} Moderator Action\n**{{action_label}}** · Case {{case_id}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "### Action Details\n- **Moderator:** {{moderator_mention}}\n- **Target:** {{target_mention}}\n- **Channel:** {{channel_mention}}\n- **Duration or scope:** {{duration_or_scope}}\n- **Action:** {{action_label}}"},
        {"type": 10, "content": "### Reason\n{{reason}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "-# Logged <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R> · Case {{case_id}}"},
        {"type": 10, "content": "{{data_quality}}"}
      ]
    }
  ]
}
```
