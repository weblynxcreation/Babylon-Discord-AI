# Wiki Response Card

Readable wiki facts with a source-provided thumbnail.

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
          "type": 9,
          "components": [
            {
              "type": 10,
              "content": "## {{title}}"
            }
          ],
          "accessory": {
            "type": 11,
            "media": {
              "url": "{{thumbnail}}"
            },
            "description": "{{title}} icon"
          }
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "{{body}}"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "-# {{footer}}"
        }
      ]
    }
  ]
}
```
