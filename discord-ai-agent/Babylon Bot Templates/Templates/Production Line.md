---
template_id: production_line
command: /production
status: draft
tags:
  - template
  - components-v2
---

# Production Line

Displays a calculated production plan with the output item's PNG in the top-right corner. Keep the layout as a code block and show direct machine-to-machine item flow. Do not invent transport entities. Each layout line is limited to 44 characters so it remains compact in Discord; use short item labels in the sketch and keep full machine details in the input-supply section.

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
              "content": "# 🏭 Production Plan\n## [{{item_name}}]({{item_wiki_url}})"
            },
            {
              "type": 10,
              "content": "**Target:** {{target_rate}} · **Machine:** {{machine_name}}"
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
          "content": "### 📋 Recipe\n**{{recipe_name}}**\n- **Output:** {{output_per_cycle}}\n- **Cycle time:** {{cycle_time}}\n- **Inputs:** {{recipe_inputs}}\n- **Input cost:** {{input_cost}}"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### ⚙️ Production Requirements\n**{{machine_count}} × {{machine_name}}** running continuously\n```text\n{{production_math}}\n```"
        },
        {
          "type": 10,
          "content": "### 📦 Continuous Input Supply\n```text\n{{input_rates}}\n```"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### 🏗️ Suggested Layout\n```text\n{{layout_sketch}}\n```"
        },
        {
          "type": 10,
          "content": "### 🗄️ Storage Buffer\n{{storage_plan}}\n-# Assumes full uptime and no production bonuses.\n-# Data: [Capital Rift Wiki]({{item_wiki_url}})"
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
