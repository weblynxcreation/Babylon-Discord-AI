# Local Discord testing (Windows)

The root project is the runtime for this test. Python and its dependencies are
already installed in `.venv`.

1. Edit `.env` locally and fill in:
   - `DISCORD_BOT_TOKEN`: the bot token for your test Discord application.
   - `NVIDIA_API_KEY`: your NVIDIA API key.
   - `DISCORD_GUILD_ID`: the numeric ID of your test server.
   - `CAPITAL_RIFT_VAULT_PATH`: the existing Capital Rift wiki folder, using forward slashes.
   - `TAVILY_API_KEY`: optional; needed for live web search.
2. Invite the test bot to that server. Enable Message Content Intent and Server
   Members Intent for the application, as described in the main README.
3. Check configuration without connecting:

   ```powershell
   .\start-local.ps1 -CheckOnly
   ```

4. Start the bot:

   ```powershell
   .\start-local.ps1
   ```

   If your PowerShell policy prevents script execution, use the Python entrypoint:

   ```powershell
   .\.venv\Scripts\python.exe scripts/local_bot.py
   ```

The launcher requires a test server ID so startup syncs slash commands to that
server. It runs the gateway bot; no local web server or tunnel is needed. Wait
for the logged-in and command-sync messages. Stop with Ctrl+C. Logs are written
to `logs/local-bot.log` and ignored by Git. Do not run another copy of the same
bot during testing, or both copies may respond.

## Test the reliability changes

- Run `/wiki-status`, then `/item` with a known item to verify the vault.
- Mention the bot with a question about that item. The log should show
  `capital_rift_wiki` in round 0 before `model_started`.
- Ask a production calculation using a recipe in the wiki. Confirm the source
  and the `calculate_production_line` tool event.
- To exercise the fallback, temporarily set `AGENT_TURN_TIMEOUT_SECONDS=0.01`,
  restart, and ask a question. Expect a timeout reply and typing to stop. Restore
  the setting to `120` and restart afterward.
- With Tavily configured, ask for a live web search and check tool events.

The default model is `meta/llama-3.3-70b-instruct`. Request/tool deadlines are
45 seconds each, within a 120-second turn budget. The check-only command validates
configuration presence, not credential validity or remote service health.

Offline regression suite (no credentials or Discord connection required):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
