---
template_id: item
command: /item
status: draft
tags:
  - template
  - components-v2
---

# Item Command

Displays an item with its wiki-hosted PNG in the top-right corner. The image URL should follow `https://wiki.capitalrift.com/icons/<item_slug>.png` unless the item data supplies another public URL.

```json
{
  "flags": 32768,
  "allowed_mentions": {
    "parse": []
  },
  "components": [
    {
      "type": 17,
      "accent_color": 13938487,
      "components": [
        {
          "type": 9,
          "components": [
            {
              "type": 10,
              "content": "# [{{item_name}}]({{item_wiki_url}})\n**{{item_category}}** · Item ID: `{{item_id}}`"
            },
            {
              "type": 10,
              "content": "{{item_description}}"
            }
          ],
          "accessory": {
            "type": 11,
            "media": {
              "url": "{{item_image_url}}"
            },
            "description": "{{item_name}} icon"
          }
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### 📊 Item Details\n```text\nStack size       {{stack_size}}\nBase value       {{base_value}}\nCurrent price    {{market_price}}\nProduced by      {{machine_name}}\n```\n{{availability_text}}"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### 🏭 Production Recipe\n**{{recipe_name}}**\n- **Output:** {{output_amount}} × {{item_name}}\n- **Cycle time:** {{cycle_time}}\n- **Rate:** {{output_rate}} per machine\n\n**Required inputs**\n{{recipe_inputs}}"
        },
        {
          "type": 10,
          "content": "### 💰 Production Economics\n```text\nInput cost       {{input_cost}}\nOutput value     {{output_value}}\nProfit/cycle     {{profit_per_cycle}}\nProfit/min       {{profit_per_minute}}\n```\n-# Values may change with market prices, upgrades, and production bonuses."
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "-# Data: [Capital Rift Wiki]({{item_wiki_url}}) · Babylon AI Item Database · Updated {{updated_at}}"
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

## Preview values

- `item_name`: Clothing Rack
- `item_id`: clothing_rack
- `item_image_url`: https://wiki.capitalrift.com/icons/clothing_rack.png
- `item_wiki_url`: https://wiki.capitalrift.com/<item-page>
