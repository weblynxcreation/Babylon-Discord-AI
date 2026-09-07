---
template_id: moderation_incident_test
status: test
tags:
  - moderation
  - components-v2
  - test
---

# Moderation Incident Test

Saved test layout for checking the mod-log presentation. This is test data only and represents no real moderation action.

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
          "content": "# 🧪 Moderation Incident\n**Template Preview** · Case TEST-001"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Action Details\n- **Member:** @ExampleUser\n- **Action:** Template Preview\n- **Rule:** N/A — test event\n- **Channel:** #mod-log-preview\n- **Duration:** None\n- **Triggered by:** Manual template test"
        },
        {
          "type": 10,
          "content": "### Evidence\n- No moderation action occurred.\n- This message verifies the Components V2 moderation layout."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "-# Logged just now · Case TEST-001"
        },
        {
          "type": 10,
          "content": "-# ✓ Test data only — no user or enforcement data was used."
        }
      ]
    }
  ]
}
```
