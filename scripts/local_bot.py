"""Validate local test configuration, then run the Discord gateway bot."""
import argparse
import logging
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
from reliability import chat_model, timeout_seconds
from observability import configure_logging


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check setup without connecting to Discord.')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    errors = []
    for name in ('DISCORD_BOT_TOKEN', 'NVIDIA_API_KEY'):
        value = os.environ.get(name, '').strip()
        if not value or value.lower().startswith(('replace', 'your-', 'your_')):
            errors.append(f'Set {name} in .env.')
    guild = os.environ.get('DISCORD_GUILD_ID', '').strip()
    if not guild.isdigit() or int(guild) <= 0:
        errors.append('Set DISCORD_GUILD_ID to your test server ID in .env (local testing uses guild command sync).')
    vault = (os.environ.get('CAPITAL_RIFT_VAULT_PATH', '').strip()
             or os.environ.get('OBSIDIAN_VAULT_PATH', '').strip())
    if not vault or not Path(vault).is_dir():
        errors.append('Set CAPITAL_RIFT_VAULT_PATH to your existing wiki folder in .env.')
    for name, default in (('NVIDIA_REQUEST_TIMEOUT_SECONDS', 45), ('AGENT_TOOL_TIMEOUT_SECONDS', 45), ('AGENT_TURN_TIMEOUT_SECONDS', 120), ('DISCORD_RESPONSE_TIMEOUT_SECONDS', 150), ('DISCORD_RECOVERY_TIMEOUT_SECONDS', 5)):
        try:
            timeout_seconds(name, default)
        except ValueError as exc:
            errors.append(str(exc))
    tavily = os.environ.get('TAVILY_API_KEY', '').strip()
    if not tavily or tavily.lower().startswith(('replace', 'your-', 'your_')):
        print('Optional: set TAVILY_API_KEY to test live web search.')
    print(f'Model: {chat_model()}')
    if errors:
        print('Local setup needs:')
        for error in errors:
            print(f'  - {error}')
        return 1
    print('Local configuration checks passed. Credentials have not been authenticated.')
    if args.check:
        return 0
    log_dir = ROOT / 'logs'
    log_dir.mkdir(exist_ok=True)
    configure_logging(log_dir)
    print('Starting bot. Press Ctrl+C to stop. Logs: logs/local-bot.log')
    runpy.run_path(str(ROOT / 'bot.py'), run_name='__main__')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
