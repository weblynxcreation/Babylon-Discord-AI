---
template_id: info_share_trading_how_to
channel: information
status: ready
tags:
  - information
  - babylon-holdings
  - trading
  - components-v2
---

# How Share Trades Work

Compact information-channel guide based on the public Babylon Holdings workflow.

```json
{
  "flags": 32768,
  "allowed_mentions": {"parse": []},
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
              "content": "# 🏛️ [How share trades work](https://holdings.thebabylon.hu/)\n### A quick guide for Babylon Holdings brokers"
            }
          ],
          "accessory": {
            "type": 11,
            "media": {"url": "{{trust_logo_url}}"},
            "description": "The Babylon Trust logo"
          }
        },
        {"type": 14, "divider": true, "spacing": 1},
        {
          "type": 10,
          "content": "## 🔎 1. Find a listing\nA listing shows that a company founder wants to sell a share. It is not an automatic sale or ownership transfer."
        },
        {
          "type": 10,
          "content": "## 🤝 2. Agree with the other broker\nUse the built-in trade conversation to settle the terms. Confirm the company, share amount, price, and who will complete the in-game transfer."
        },
        {
          "type": 10,
          "content": "## ✅ 3. Transfer, then both confirm\nThe buyer and seller complete the ownership change in Capital Rift first. Both sides then confirm it happened in Babylon Holdings. The ledger updates only after both confirmations."
        },
        {
          "type": 10,
          "content": "## ⚖️ Know the rules\n- Only a company founder can list company shares.\n- Purchased shares cannot be resold through Babylon Holdings.\n- A 5% commission applies to each side of a completed trade.\n- Open a support ticket if the other broker does not complete their side."
        },
        {
          "type": 10,
          "content": "-# 🔐 Trade carefully: Babylon records what both brokers confirm; it does not independently verify the Capital Rift transfer."
        },
        {"type": 14, "divider": true, "spacing": 1},
        {
          "type": 10,
          "content": "-# Guide: [Babylon Holdings](https://holdings.thebabylon.hu/) · Updated <t:{{timestamp_unix}}:f> · <t:{{timestamp_unix}}:R>"
        },
        {"type": 10, "content": "{{data_quality}}"}
      ]
    }
  ]
}
```
