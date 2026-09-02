# Babylon Exchange

Babylon Exchange connects the Babylon Stock Market and Capital Rift with a
Discord bot. The bot keeps its existing agentic chat and moderation features
while exposing public, read-only market data through Discord slash commands.

## Repository layout

- `discord-ai-agent/` — Python `discord.py` bot, Babylon API client, market
  commands, moderation, AI tools, and tests.
- `babylon-extension/` — Manifest V3 browser extension that links a Babylon
  account to Capital Rift and relays company verification data to the Babylon
  backend.

## Market commands

- `/market`
- `/stock <company>`
- `/leaders <metric> [limit]`
- `/movers [limit]`
- `/market-status`

Authenticated portfolio and trading commands are intentionally deferred until
the Babylon backend provides secure Discord account linking with scoped,
revocable authorization.

## Run the Discord bot locally

```powershell
cd discord-ai-agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Fill in the local .env without committing it.
.\.venv\Scripts\python.exe bot.py
```

Set `DISCORD_GUILD_ID` during development for immediate guild-only slash-command
synchronization. Leave it empty when synchronizing global production commands.

## Hosting architecture

The Discord bot maintains an outbound gateway connection and must run on
persistent compute. Vercel Functions scale to zero and enforce finite invocation
durations, so they are not used for the always-on bot process. Vercel can host a
future public dashboard, documentation site, or HTTP interaction service, while
the gateway bot runs on a persistent worker host.

## Security

- Never commit `.env`, Discord tokens, API keys, Capital Rift cookies, runtime
  databases, virtual environments, or generated archives.
- Rotate any credential that has appeared in an earlier ZIP or Git history.
- The Discord bot must never receive or store a Capital Rift session cookie.
