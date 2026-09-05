---
template_id: moderation_raid_detected
channel: mod-log
status: draft
tags:
  - template
  - raid-protection
  - components-v2
---

# Raid Detected

Use when join volume activates raid mode.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
  "components": [
    {
      "type": 17,
      "accent_color": "{{accent_color}}",
      "components": [
        {"type": 10, "content": "# 🚨 Raid Detected\n**Raid mode is ON** · Case {{case_id}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "### Detection Details\n- **Recent joins:** {{join_count}}\n- **Detection window:** {{window_seconds}}\n- **Screening action:** {{raid_action}}\n- **Minimum account age:** {{minimum_account_age}}\n- **Status:** {{raid_mode_status}}"},
        {"type": 10, "content": "### Moderator Action\n{{next_step}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "-# Logged <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R> · Case {{case_id}}"},
        {"type": 10, "content": "{{data_quality}}"}
      ]
    }
  ]
}
```
