# Discord AI Agent — Full Setup & Run Guide

Everything needed to go from a fresh zip file to a running bot with chat,
live web search/scraping, image/GIF generation, code building, moderation,
and raid protection.

---

## Part 1: Prerequisites

- **Python 3.10+** installed. Check with: `python --version` (Windows) or
  `python3 --version` (Mac/Linux). Get it from python.org if missing —
  on Windows, check "Add python.exe to PATH" during install.
- A Discord account with a server you manage (or can create one for free).
- Accounts (free) at **build.nvidia.com** and **tavily.com**.

---

## Part 2: Create the Discord bot application

1. Go to https://discord.com/developers/applications → **New Application**,
   name it anything.
2. Open the **Bot** tab → **Reset Token** → copy the token somewhere safe.
   This is your `DISCORD_BOT_TOKEN`. You can't view it again without
   resetting it.
3. On the same tab, scroll to **Privileged Gateway Intents** and enable:
   - **Message Content Intent** (bot needs this to read chat messages)
   - **Server Members Intent** (needed for raid protection to see joins)
4. Go to **OAuth2 → URL Generator**. Under Scopes check:
   - `bot`
   - `applications.commands`
   Under Bot Permissions check:
   - Send Messages, Attach Files, Read Message History, Use Slash Commands
   - Manage Messages, Timeout Members, Kick Members, Ban Members
     *(these last four are for moderation/raid protection — skip if you
     only want chat/image/GIF features)*
5. Copy the generated URL at the bottom, open it in a browser, and add the
   bot to your server.

---

## Part 3: Get your API keys

| Key | Where to get it | Used for |
|---|---|---|
| `NVIDIA_API_KEY` | build.nvidia.com → sign in → generate a key from any model page | Chat brain + image/GIF generation |
| `TAVILY_API_KEY` | tavily.com → sign up → API key on your dashboard | Live web search |

Both have free tiers with no credit card required to start.

---

## Part 4: Install the project

**Windows (Command Prompt):**
```cmd
cd path\to\discord-ai-agent
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**Mac/Linux:**
```bash
cd path/to/discord-ai-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## Part 5: Configure `.env`

Open `.env` in a text editor (`notepad .env` on Windows) and fill in:

```
DISCORD_BOT_TOKEN=<your token from Part 2>
NVIDIA_API_KEY=<your key from Part 3>
TAVILY_API_KEY=<your key from Part 3>
```

No `Bearer` prefix, no quotes — just the raw key/token after the `=`.

**Check `NVIDIA_CHAT_MODEL` is a currently-active model.** NVIDIA retires
older models regularly (e.g. `meta/llama-3.1-70b-instruct` was deprecated
Aug 2026). Good current options:
- `nvidia/nemotron-3-ultra-550b-a55b` — best quality, confirmed reliable
  tool/function calling (recommended default)
- `nvidia/nemotron-3.5-lightning-30b-a3b` — smaller/faster
- `meta/llama-3.2-90b-vision-instruct` — works, but it's a vision-focused
  model; NVIDIA notes vision-only models sometimes only partially support
  tool calling, which this bot depends on for everything. Test it (Part 7)
  before relying on it.

If you ever see an error like `Error code: 410 ... has reached its end of
life`, that means whatever model is set has been retired — check
build.nvidia.com/models for its replacement and update this line.

Leave everything else in `.env` as-is unless you want to change defaults
(history length, image model, etc).

---

## Part 6: Run it

```
python bot.py
```

You should see:
```
Logged in as YourBotName (id=123456789)
```

That means it's connected. Leave this terminal window open — closing it
stops the bot.

---

## Part 7: Test it

- **Chat**: @mention the bot in a channel, or DM it. Ask something that
  needs a live answer (e.g. "what's the date today") to confirm it's
  actually calling `web_search` rather than guessing.
- **Images**: `/image a red fox in a forest`
- **GIFs**: `/gif a candle flickering`
- **Code**: `/build a simple single-page HTML portfolio site`
- **Moderation**: `/automod settings` and `/raid config` to see current
  defaults (both require Manage Server permission on your account).
- **Memory**: chat a bit, restart the bot (Ctrl+C, then `python bot.py`
  again), and confirm it still remembers the conversation — history now
  persists to disk.

---

## Part 8: Deploy to a VPS (optional, for 24/7 uptime)

```bash
# on the VPS:
git clone <your-repo-or-scp-the-folder> /opt/discord-ai-agent
cd /opt/discord-ai-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # fill in your real values
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

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now discord-ai-agent
journalctl -u discord-ai-agent -f   # live logs
```

Back up the `data/` folder occasionally — it holds your moderation
settings and chat history, and won't come from a fresh copy of the zip.

---

## Troubleshooting

| Error / symptom | Cause | Fix |
|---|---|---|
| `'cp' is not recognized` | Using `cp` on Windows | Use `copy` instead |
| `KeyError: 'DISCORD_BOT_TOKEN'` | `.env` missing or not filled in, or not running from the project folder | Confirm `.env` exists in the same folder as `bot.py` and has the token set |
| `Error code: 410 ... end of life` | The model in `NVIDIA_CHAT_MODEL` was retired by NVIDIA | Check build.nvidia.com/models, swap in a current model |
| `PrivilegedIntentsRequired` | Server Members Intent not enabled | Enable it in the Bot tab of the Developer Portal (Part 2, step 3) |
| Bot online but never responds to mentions | Message Content Intent not enabled | Same tab, enable it |
| Slash commands not showing in Discord | First-sync delay | Wait a few minutes, or restart the bot once |
| Bot can't kick/ban/timeout/delete messages | Missing permissions | Re-invite using the URL from Part 2 with all permissions checked |
| "You don't have permission to use this command" | Your Discord account lacks the required permission (Manage Server, Kick Members, etc.) | Use an account with the right server role |
