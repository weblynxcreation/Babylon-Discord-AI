Vercel (Interactions endpoint)

Overview
- Vercel serverless is suitable for Discord "interactions" (slash commands) because Discord can deliver requests to an HTTPS endpoint.
- Vercel is NOT suitable for running a long‑lived websocket client (the classic Discord bot). Use Railway/Render for the full bot.

Files added:
- api/interactions.py  -- Flask handler that verifies Discord signatures and responds to interactions
- vercel-requirements.txt -- minimal deps for the Vercel function
- Procfile -- example Procfile for persistent hosts

Vercel deployment steps
1. In the Discord Developer Portal, set your application interaction endpoint to: https://<your-vercel-app>.vercel.app/api/interactions
2. In Vercel project settings, set Environment Variable DISCORD_PUBLIC_KEY to your application public key (hex). Do NOT commit secrets to the repo.
3. On Vercel, when prompted for Build & Output settings, use the default. Vercel will detect Python functions in the api/ folder.
4. Set the project to install the requirements from vercel-requirements.txt by adding a build step or pinning it as the repository requirements file. Alternatively, add these deps to your main requirements.txt.
5. Deploy and test by calling the endpoint or registering and running a slash command. Use /interactions and observe responses.

Local testing
- Install deps: pip install -r vercel-requirements.txt
- Run locally: export DISCORD_PUBLIC_KEY=<hex-key> && flask --app api.interactions run --port 3000
- Use a tunneling tool (ngrok) to expose localhost to Discord for testing and set the interaction endpoint accordingly.

Persistent hosting for the full bot (recommended for the current codebase)
- The existing bot (bot.py) uses a persistent websocket connection and must run on a host that supports long-running processes.
- Example hosts: Railway, Render, Fly.io, or a VPS. For Heroku-style hosts use a Procfile.

Example Procfile (added to repo):
worker: python bot.py

Railway/Render quickstart
1. Create a new project on Railway or Render and connect the GitHub repo.
2. Set the environment variable DISCORD_BOT_TOKEN (and any other secrets: OPENAI_API_KEY, etc.) in the service settings.
3. For Railway, set the start command to: python bot.py
4. Deploy the service — it will run the bot as a persistent worker.

Security and notes
- Never commit DISCORD_BOT_TOKEN or DISCORD_PUBLIC_KEY to the repository.
- For Vercel interactions, responses must be returned within a few seconds. For longer processing, respond with a deferred acknowledgement and process asynchronously.

If you want, next actions:
- Add automatic forwarding from interactions endpoint to the full bot (webhook bridge).
- Add a GitHub Actions workflow that deploys to Vercel automatically on push to main.
