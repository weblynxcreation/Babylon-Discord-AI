---
status: ready
tags:
  - babylon-bot
  - slash-commands
  - components-v2
---

# Slash Command Index

Every registered slash command now has a dedicated Components V2 template note in this folder. The bot integration remains a separate implementation step.

| Command | Template | Status |
| --- | --- | --- |
| `/ask` | [[Ask]] | Ready |
| `/market` | [[Market]] | Ready |
| `/stock` | [[Stock]] | Ready |
| `/leaders` | [[Leaders]] | Ready |
| `/movers` | [[Movers]] | Ready |
| `/market-status` | [[Market Status]] | Ready |
| `/image` | [[Image]] | Ready |
| `/gif` | [[GIF]] | Ready |
| `/clearhistory` | [[Clear History]] | Ready |
| `/build` | [[Build]] | Ready |
| `/automod toggle` | [[Automod Toggle]] | Ready |
| `/automod addword` | [[Automod Add Word]] | Ready |
| `/automod removeword` | [[Automod Remove Word]] | Ready |
| `/automod settings` | [[Automod Settings]] | Ready |
| `/raid mode` | [[Raid Mode]] | Ready |
| `/raid config` | [[Raid Config]] | Ready |
| `/modlog` | [[Mod Log]] | Ready |
| `/warn` | [[Warn]] | Ready |
| `/timeout` | [[Timeout]] | Ready |
| `/kick` | [[Kick]] | Ready |
| `/ban` | [[Ban]] | Ready |
| `/purge` | [[Purge]] | Ready |

## Shared rules

- Use only verified command data; include `data_quality` warnings for unavailable values.
- Use Discord user and channel mentions from snowflake IDs with notifications disabled by default.
- Use `<t:UNIX:f>` and `<t:UNIX:R>` for timestamps.
- Keep code-block diagrams compact: 44 characters or fewer per line.
