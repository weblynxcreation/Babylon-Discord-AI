---
template_id: agentic_investment_analysis
channel: response
status: draft
tags:
  - template
  - agentic-response
  - investment
  - components-v2
---

# Investment Analysis

Use for questions such as “What is best for a $1 million investment?” Populate every value from current, cited game data. Do not estimate unknown costs or claim a recommendation is optimal when comparison data is incomplete. Present comparison data as visual metric rows, never a Markdown table.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
  "components": [
    {
      "type": 17,
      "accent_color": "{{accent_color}}",
      "components": [
        {"type": 9, "components": [{"type": 10, "content": "# 📈 Investment Analysis\n**Question:** {{question}}"}], "accessory": {"type": 11, "media": {"url": "{{item_image_url}}"}}},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "### Recommendation\n[**{{recommended_item}}**]({{item_wiki_url}}) · {{machine_name}}\n- **Machine cost:** {{machine_cost}}\n- **Profit per minute:** {{profit_per_minute}}\n- **Return per investment dollar:** {{profit_per_dollar}}\n- **At the stated budget:** {{investment_outcome}}"},
        {"type": 10, "content": "### Comparison at the stated budget\n{{comparison_visual}}"},
        {"type": 10, "content": "### Why this is recommended\n{{recommendation_reasoning}}"},
        {"type": 10, "content": "### Build plan\n{{build_steps}}"},
        {"type": 10, "content": "### Assumptions and limits\n{{constraints}}"},
        {"type": 14, "divider": true, "spacing": 1},
        {"type": 10, "content": "-# Data: [{{source_attribution}}]({{item_wiki_url}}) · Generated <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R>"},
        {"type": 10, "content": "{{data_quality}}"}
      ]
    }
  ]
}
```

## Comparison-row format

Use one compact block per verified option. Scale the bar only from verified values and name its metric.

```text
🏆 **Standard Window** — $6,105/min
`████████████████████` Return at $1M
- 1,794 Carpentry Benches · $558 each

**Motherboard** — $2,137/min
`███████░░░░░░░░░░░░░` Return at $1M
- 625 Electronics Benches · $1,600 each
```
