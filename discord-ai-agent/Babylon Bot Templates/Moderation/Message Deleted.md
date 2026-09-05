---
template_id: moderation_message_deleted
channel: mod-log
status: draft
tags:
  - template
  - moderation
  - message-deleted
  - components-v2
---

# Message Deleted

Use when automod or a moderator removes a message. Log the moderation reason and message metadata; do not reproduce harmful deleted content in the mod-log template.

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
          "content": "# 🗑️ Message Deleted\nDeleted message from {{member_mention}} · {{moderation_source}}"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Action Details\n- **Channel:** {{channel_mention}}\n- **Violation:** {{violation_number}}\n- **Rule:** {{rule_name}}\n- **Message ID:** {{message_id}}\n- **Action:** {{action_label}}"
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

## Example

Pass Discord-formatted values such as `<@123456789012345678>` and `<#123456789012345678>` for the member and channel. The template renders them as clickable mentions without sending notifications.
