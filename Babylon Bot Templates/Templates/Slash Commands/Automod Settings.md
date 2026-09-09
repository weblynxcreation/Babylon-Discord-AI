---
template_id: slash_automod_settings
command: /automod settings
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /automod settings

Use for the current automod configuration. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`automod_status`, `banned_words`, `enforcement_policy`, `timestamp_unix`, `data_quality`

```json
{
  "flags": 32768,
  "allowed_mentions": {
    "parse": []
  },
  "components": [
    {
      "type": 17,
      "accent_color": 3447003,
      "components": [
        {
          "type": 10,
          "content": "# ⚙️ /automod settings\nUse for the current automod configuration."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Automod status\n{{automod_status}}"
        },
        {
          "type": 10,
          "content": "### Banned words\n{{banned_words}}"
        },
        {
          "type": 10,
          "content": "### Enforcement policy\n{{enforcement_policy}}"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "-# Generated <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R>"
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
