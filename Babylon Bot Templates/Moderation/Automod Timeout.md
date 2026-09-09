---
template_id: moderation_automod_timeout
channel: mod-log
status: draft
tags:
  - template
  - automod
  - timeout
  - components-v2
---

# Automod Timeout

Use when repeated automod violations reach the timeout threshold.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
  "components": [
    {
      "type": 17,
      "accent_color": "{{accent_color}}",
      "components": [
        {"type": 10, "content": "# ⏱️ Automod Timeout\n{{member_mention}} · Case {{case_id}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "### Escalation Details\n- **Duration:** {{duration}}\n- **Violation count:** {{violation_count}}\n- **Latest violation:** {{latest_violation}}\n- **Channel:** {{channel_mention}}\n- **Triggered by:** Automod"},
        {"type": 10, "content": "### Reason\n{{reason}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "-# Logged <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R> · Case {{case_id}}"},
        {"type": 10, "content": "{{data_quality}}"}
      ]
    }
  ]
}
```
