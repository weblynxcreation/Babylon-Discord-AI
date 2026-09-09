---
template_id: moderation_raid_join_action
channel: mod-log
status: draft
tags:
  - template
  - raid-protection
  - join-screening
  - components-v2
---

# Raid Join Action

Use when raid mode screens a new account and kicks, bans, or alerts moderators.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
  "components": [
    {
      "type": 17,
      "accent_color": "{{accent_color}}",
      "components": [
        {"type": 10, "content": "# {{action_emoji}} Raid Join Screened\n{{member_mention}} · Case {{case_id}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "### Account Details\n- **Member ID:** {{member_id}}\n- **Account age:** {{account_age}}\n- **Required age:** {{minimum_account_age}}\n- **Action:** {{action_label}}\n- **Raid mode:** {{raid_mode_status}}"},
        {"type": 10, "content": "### Reason\n{{reason}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "-# Logged <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R> · Case {{case_id}}"},
        {"type": 10, "content": "{{data_quality}}"}
      ]
    }
  ]
}
```
