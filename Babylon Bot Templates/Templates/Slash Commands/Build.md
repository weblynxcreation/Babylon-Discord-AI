---
template_id: slash_build
command: /build
status: ready
tags:
  - template
  - slash-command
  - components-v2
---

# /build

Use for a completed build request or a build result that needs a download link. Use only returned or verified values. If a field is unavailable, state that in its value and set `data_quality` to a warning. Mentions must use Discord snowflake syntax and remain non-pinging.

## Required placeholders

`build_request`, `build_result`, `download_url`, `timestamp_unix`, `data_quality`

```json
{
  "flags": 32768,
  "allowed_mentions": {
    "parse": []
  },
  "components": [
    {
      "type": 17,
      "accent_color": 5763719,
      "components": [
        {
          "type": 10,
          "content": "# 🛠️ /build\nUse for a completed build request or a build result that needs a download link."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### Request\n{{build_request}}"
        },
        {
          "type": 10,
          "content": "### Result\n{{build_result}}"
        },
        {
          "type": 10,
          "content": "### Download\n[Download build]({{download_url}})"
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
