---
template_id: slash_raid_config
command: /raid config
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /raid config

Use for the current raid-protection configuration. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`detection_settings`, `screening_settings`, `raid_mode_status`, `timestamp_unix`, `data_quality`

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
          "content": "# ⚙️ /raid config\nUse for the current raid-protection configuration."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Detection settings\n{{detection_settings}}"
        },
        {
          "type": 10,
          "content": "### Screening settings\n{{screening_settings}}"
        },
        {
          "type": 10,
          "content": "### Current mode\n{{raid_mode_status}}"
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
