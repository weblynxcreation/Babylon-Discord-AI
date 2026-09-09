---
tags:
  - babylon-bot
  - components-v2
---

# Babylon Bot Templates

This vault contains the shared Discord Components V2 messages used across Babylon AI. It is independent of the Capital Rift wiki. Wiki-hosted item images are external assets referenced by URL.

## Templates

- [[Information/Babylon Holdings How To|Babylon Holdings How To]] — information-channel guide to the public Babylon Holdings workflow.
- [[Information/How Share Trades Work|How Share Trades Work]] — information-channel guide to listings and confirmed share trades.
- [[Templates/Slash Commands/Index|Slash Command Index]] — planning inventory for every registered slash command; individual command templates are not started.
- [[Agentic/Investment Analysis|Investment Analysis]] — source-backed answer for a budget or factory investment question.
- [[Slash Commands/Command Confirmation|Command Confirmation]] — completed command action, outcome, and next step.
- [[Slash Commands/Settings Summary|Settings Summary]] — current automod, raid, and bot configuration.
- [[Slash Commands/Command Error|Command Error]] — validation, permission, and unavailable-data response.
- [[Templates/Item Command|Item Command]] — item identity, production details, economics, and a top-right item thumbnail.
- [[Templates/Production Line|Production Line]] — target-rate calculations, required inputs, layout, and storage.
- [[Templates/Moderation Incident|Moderation Incident]] — mod-log events for automod, raids, and moderator actions.
- [[Moderation/Incident Test|Incident Test]] — saved test-only moderation layout.
- [[Moderation/Message Deleted|Message Deleted]] — mod-log record for removed messages.
- [[Moderation/Automod Timeout|Automod Timeout]] — repeat-violation escalation.
- [[Moderation/Raid Detected|Raid Detected]] — raid-mode activation.
- [[Moderation/Raid Join Action|Raid Join Action]] — raid-mode screening outcome.
- [[Moderation/Moderator Action|Moderator Action]] — warnings, manual timeouts, kicks, bans, and purges.
- [[Moderation/Permission Error|Permission Error]] — failed moderation actions requiring staff attention.

## References

- [[Reference/Style Guide|Style Guide]]
- [[Reference/Placeholder Dictionary|Placeholder Dictionary]]

## Editing workflow

1. Open this folder as an Obsidian vault.
2. Edit the JSON code block in the applicable template note.
3. Keep placeholder names wrapped in double braces, such as `{{item_name}}`.
4. Run the bot tests before committing a template change.

The Python loader reads the first `json` code block in each template note. Keep explanatory examples in other code-block languages so they are not mistaken for the live payload.
