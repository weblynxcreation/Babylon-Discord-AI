---
template_id: slash_command_confirmation
channel: interaction-response
status: draft
tags:
  - template
  - slash-command
  - confirmation
  - components-v2
---

# Command Confirmation

Use after a slash command completes a change, such as `/warn`, `/timeout`, `/kick`, `/ban`, `/purge`, `/automod toggle`, `/raid mode`, or `/modlog`.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
  "components": [
    {
      "type": 17,
      "accent_color": 5763719,
      "components": [
        {"type": 10, "content": "# ✓ {{result_title}}\n**/{{command_name}}** completed successfully."},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "### Result\n{{result_details}}"},
        {"type": 10, "content": "### Next step\n{{next_step}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "-# Completed <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R>"},
        {"type": 10, "content": "{{data_quality}}"}
      ]
    }
  ]
}
```
