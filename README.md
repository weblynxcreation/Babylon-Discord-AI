# Discord AI Agent

A Discord bot that chats naturally, searches the live web for current info,
generates images, and writes + packages code/websites as downloadable zips —
powered by your NVIDIA NIM API key.

## What it does

- **Chat**: mention the bot or DM it — it remembers the conversation per
  channel/DM **and now persists it to disk**, so restarting the bot doesn't
  wipe context. Run `/clearhistory` in any channel to make it forget that
  channel's conversation on purpose.
- **`/ask <question>`**: one-off question, live web search included
- **`/image <prompt>`**: generates and posts an image
- **`/gif <prompt>`**: generates a short looping animated GIF
- **`/build <description>`**: writes real code/website files and sends a zip
- **Web scraping**: give it a URL and it'll fetch and read the actual page
  content (not just a search snippet) — reads text or pulls out links,
  respects `robots.txt`, and skips anything behind a login or paywall
- **Obsidian vault search** (optional): if you set `OBSIDIAN_VAULT_PATH` in `.env`,
  the bot can search and read your local Obsidian notes. Just ask it questions
  and it'll automatically find answers from your vault. Example: *"How many foundries do I need to smelt 1000 iron bars per minute?"*
- **Automod**: filters banned words, mass mentions, invite-link spam, and
  message-rate spam in real time, with escalating enforcement (delete →
  warn → 10-minute timeout for repeat offenders)
- **AI-powered moderation** (opt-in, `/automod ai-toggle`): sends messages
  that pass keyword automod through the LLM as a moderation classifier, so
  it catches harassment, hate speech, threats, and self-harm talk that's
  phrased in ways no banned-word list would catch. Severity-based response
  (none/low/medium/high) — see the "AI-powered moderation" section below.
- **Raid protection**: detects join bursts and, once triggered, auto-kicks
  (or bans, or just alerts — configurable) new accounts below a minimum age
  until a moderator clears it
- Automatically decides *when* to search the web, scrape URLs, search Obsidian,
  generate images/GIFs, or write code — you don't need separate commands for
  the chat flow, only mention it.

## 1. Create the Discord application

1. Go to https://discord.com/developers/applications → **New Application**
2. **Bot** tab → **Reset Token**, copy it → this is `DISCORD_BOT_TOKEN`
3. On the same tab, enable **Message Content Intent** and **Server Members
   Intent** (both under Privileged Gateway Intents) — Server Members Intent
   is required for raid protection to see who's joining
4. **OAuth2 → URL Generator**: check `bot` and `applications.commands` scopes,
   then under Bot Permissions check: Send Messages, Attach Files, Read Message
   History, Use Slash Commands, **Manage Messages, Timeout Members, Kick
   Members, Ban Members** (the last four are needed for moderation/raid
   protection — skip them if you only want the chat/image/GIF features)
5. Open the generated URL to invite the bot to your server

## 2. Get your API keys

- **NVIDIA NIM**: you already have this from Agentic Hub — reuse the same key
- **Tavily** (web search): free tier at https://tavily.com — built specifically
  for feeding search results to LLM agents, works better than raw scraping
- Image gen uses the same NVIDIA key by default (NIM-hosted Stable Diffusion 3).
  `STABILITY_API_KEY` in `.env` is optional — only needed as a fallback.

## 2a. Optional: Obsidian Vault Integration

If you have an Obsidian vault with personal knowledge (game guides, wiki notes, worldbuilding, etc.),
the bot can search and read from it automatically when answering questions.

1. In `.env`, set `OBSIDIAN_VAULT_PATH` to your vault's root directory:
   ```
   OBSIDIAN_VAULT_PATH=C:\Users\yourname\OneDrive\Documents\Obsidian Vault\YourVaultName
   ```
   
   Or for Linux/Mac:
   ```
   OBSIDIAN_VAULT_PATH=/Users/yourname/Obsidian Vaults/YourVaultName
   ```

2. That's it. The bot now uses `obsidian_search` first for questions about topics in your vault,
   then falls back to the live web if needed. It searches all `.md` files recursively.

## 3. Local setup

```bash
cd discord-ai-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and fill in your keys
python bot.py
```

## 4. Deploy on your VPS (systemd)

```bash
# On the VPS, as your deploy user:
git clone <your-repo-or-scp-the-folder> /opt/discord-ai-agent
cd /opt/discord-ai-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # fill in real values
```

Create `/etc/systemd/system/discord-ai-agent.service`:

```ini
[Unit]
Description=Discord AI Agent Bot
After=network.target

[Service]
Type=simple
User=YOUR_LINUX_USER
WorkingDirectory=/opt/discord-ai-agent
ExecStart=/opt/discord-ai-agent/venv/bin/python bot.py
Restart=on-failure
RestartSec=5
EnvironmentFile=/opt/discord-ai-agent/.env

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now discord-ai-agent
sudo systemctl status discord-ai-agent
journalctl -u discord-ai-agent -f   # live logs
```

## Notes on web scraping

`scrape_url` is meant for pages you already have a link to — it doesn't crawl
or discover pages on its own (that's what `web_search` is for). It checks
`robots.txt` before every fetch and will refuse to scrape a page that
disallows it, and it can't get past logins or paywalls (nor is it meant to).
Pulled content is capped at ~6000 characters per page so one scrape doesn't
eat the whole context window.

## Moderation & raid protection

These run automatically once the bot is in your server with the right
permissions (see step 2 above) — no setup required beyond that, though
everything's configurable.

**Automod** (`/automod toggle`, `/automod addword`, `/automod removeword`,
`/automod settings`): scans every message for banned words, invite-link
spam, mass mentions (default: >5), and message-rate spam (default: >6
messages/10s). First couple of violations get the message deleted with a
DM'd warning; the 3rd violation in a short window escalates to a 10-minute
timeout automatically.

**Raid protection** (`/raid mode`, `/raid config`): watches for a burst of
joins (default: 8 joins within 15 seconds — classic raid pattern). Once
triggered, it screens every further join against a minimum account age
(default: 24 hours) and kicks, bans, or just alerts on anything newer,
depending on how you've configured `action`. Stays on until a moderator
runs `/raid mode enabled:False`.

**AI-powered moderation** (`/automod ai-toggle`, `/automod ai-settings`):
off by default. Once turned on, every message that passes keyword automod
and is at least `ai_automod_min_chars` long (default 12) gets one extra LLM
call using your existing `NVIDIA_API_KEY`, with a system prompt that treats
the message purely as data to classify — it never follows instructions
contained in the message being checked. The model scores the message on
harassment, hate, sexual content, violence, and self-harm, then returns an
overall severity:

| Severity | What happens |
|---|---|
| `none` | Nothing — most messages land here |
| `low` | Optional quiet mod-log entry only (toggle with `log_low_severity`); no action taken |
| `medium` | Message deleted, user DM'd, counts as one strike toward the same 3-strike timeout ladder keyword automod uses |
| `high` | Message deleted **and** an immediate 10-minute timeout, regardless of prior strikes (direct threats, explicit hate speech, self-harm intent) |

Because it shares the violation counter with keyword automod, a mix of
rule-based and AI-flagged violations escalates together rather than each
resetting the other's count. Any classifier failure (API error, timeout,
bad JSON) is treated as `none` — a flaky call never itself becomes an
incident, and keyword automod keeps running underneath it regardless. This
does add one LLM call per checked message, so it's opt-in and gated by
`ai_automod_min_chars` to skip trivial one-word messages.

**Manual moderation commands**: `/warn`, `/timeout`, `/kick`, `/ban`,
`/purge` — all require the matching Discord permission (Moderate Members,
Kick Members, Ban Members, Manage Messages respectively) and log to your
mod-log channel.

**Mod log**: run `/modlog #your-channel` once to have all of the above
(automod actions, raid events, manual mod commands) posted there. Without
it, events just go to the bot's own console logs.

All moderation settings are stored per-server in `data/moderation_config.json`
(created automatically) so they survive restarts.

## Persistent chat memory

Conversation history is stored per Discord channel/DM in
`data/chat_history.db` (SQLite, created automatically) — no extra database
setup needed. Each channel keeps its most recent `HISTORY_LIMIT` messages
(set in `.env`, default 20); older ones are trimmed automatically. Delete
the `data/` folder any time to wipe everything, or use `/clearhistory` to
reset just one channel.

## Notes on model choice

`NVIDIA_CHAT_MODEL` in `.env` must support tool/function calling — every
feature in this bot (search, scraping, image/GIF gen, code packaging) is
driven through tool calls, so this is the one setting that can silently
break everything if it's wrong.

Confirmed-good agentic options: `nvidia/nemotron-3-ultra-550b-a55b` (best
quality, NVIDIA's own flagship for agentic/tool-calling work) or
`nvidia/nemotron-3.5-lightning-30b-a3b` (smaller/faster).

**Currently set to `meta/llama-3.2-90b-vision-instruct`** per request — this
is a real free NIM endpoint, but it's a *vision* model (image+text in, text
out), and NVIDIA's own docs note vision-only models often only partially
support function calling. Test it first: mention the bot with something
that needs a live search (e.g. "what's today's date") and confirm it
actually searches rather than just answering from training data. If tool
calls don't fire reliably, switch `NVIDIA_CHAT_MODEL` back to
`nvidia/nemotron-3-ultra-550b-a55b` — the vision model's real strength is
looking at images you send it, which this bot doesn't currently do anything
with unless you extend it to.

## Extending it

- **More tools**: add a new file in `tools/`, export a `TOOL_SCHEMA` dict and
  an async function, then register both in `agent.py`'s `TOOLS` list and
  `TOOL_IMPLS` dict. The agent loop picks it up automatically.
- **Persistent memory across restarts**: currently conversation history is
  in-memory per channel and resets on bot restart. Swap `channel_history`
  for a SQLite table if you want it to persist.
- **Task automation**: for scheduled/recurring tasks (not just reactive chat),
  add `discord.ext.tasks` loops in `bot.py` that call `run_agent` on a timer.
- **Better GIFs**: `generate_gif` approximates animation by generating several
  still frames independently and stitching them — motion won't be perfectly
  coherent between frames. If a proper free-hosted text-to-video/GIF model
  becomes available on NIM, swap the implementation in `tools/gif_gen.py`.

## Integrated Babylon features

The root bot is the canonical runtime. It includes:

- Read-only Babylon market commands and AI market lookup
- Per-server setup and bot-admin configuration
- A read-only Capital Rift Obsidian vault index and production calculator
- Optional AI-assisted moderation from the upstream bot
- Discord OAuth account-linking API contract for the Babylon website team

Configuration templates are in [`.env.example`](.env.example). See
[`docs/OBSIDIAN_VAULT_SETUP.md`](docs/OBSIDIAN_VAULT_SETUP.md) for local wiki setup and
[`docs/DISCORD_ACCOUNT_LINKING_API.md`](docs/DISCORD_ACCOUNT_LINKING_API.md) for the website contract.

Runtime files under `data/` are intentionally ignored. Deployments must use persistent storage if
moderation settings or chat history need to survive restarts.
