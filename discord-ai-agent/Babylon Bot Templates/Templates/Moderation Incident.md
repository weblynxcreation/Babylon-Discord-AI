---
template_id: moderation_incident
channel: mod-log
status: draft
tags:
  - template
  - moderation
  - components-v2
---

# Moderation Incident

Use for automod matches, raid protection events, warnings, timeouts, kicks, bans, and purges. The command selects an RGB accent color: yellow for review, orange for active enforcement, red for critical action, and green for resolved cases.

```json
{
  "flags": 32768,
  "allowed_mentions": {
    "parse": []
  },
  "components": [
    {
      "type": 17,
      "accent_color": "{{accent_color}}",
      "components": [
        {
          "type": 10,
          "content": "# {{severity_emoji}} Moderation Incident\n**{{action_label}}** · Case {{case_id}}"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Action Details\n- **Member:** {{member_mention}}\n- **Action:** {{action_label}}\n- **Rule:** {{rule_name}}\n- **Channel:** {{channel_mention}}\n- **Duration:** {{duration}}\n- **Triggered by:** {{source_system}}"
        },
        {
          "type": 10,
          "content": "### Evidence\n{{evidence}}"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "-# Logged <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R> · Case {{case_id}}"
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

## Accent colors

| Event state | Value |
| --- | ---: |
| Review required | 16705372 |
| Enforcement active | 15105570 |
| Critical | 15158332 |
| Resolved | 5763719 |
