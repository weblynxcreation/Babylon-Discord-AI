"""
Per-guild moderation configuration, persisted to a local JSON file so
settings survive bot restarts. No database server needed — this is small,
low-write-volume data (config + warning counts), so a JSON file with an
asyncio lock is plenty.
"""
import json
import os
import asyncio

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CONFIG_PATH = os.path.join(DATA_DIR, "moderation_config.json")

DEFAULT_GUILD_CONFIG = {
    "automod_enabled": True,
    "banned_words": [],
    "max_mentions": 5,
    "max_messages_per_10s": 6,
    "block_invite_links": True,
    "mod_log_channel_id": None,
    "raid_protection_enabled": True,
    "raid_join_threshold": 8,
    "raid_join_window_seconds": 15,
    "raid_min_account_age_hours": 24,
    "raid_action": "kick",  # "kick", "ban", or "alert_only"
    "raid_mode_active": False,
    "warnings": {},  # {user_id_str: count}
}

_lock = asyncio.Lock()
_cache: dict = {}


def _load():
    global _cache
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    else:
        _cache = {}


def _save():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(_cache, f, indent=2)


_load()


async def get_guild_config(guild_id: int) -> dict:
    async with _lock:
        key = str(guild_id)
        if key not in _cache:
            _cache[key] = json.loads(json.dumps(DEFAULT_GUILD_CONFIG))
            _save()
        # Backfill any new default keys for guilds configured before an update
        merged = json.loads(json.dumps(DEFAULT_GUILD_CONFIG))
        merged.update(_cache[key])
        return merged


async def update_guild_config(guild_id: int, **kwargs) -> dict:
    async with _lock:
        key = str(guild_id)
        if key not in _cache:
            _cache[key] = json.loads(json.dumps(DEFAULT_GUILD_CONFIG))
        _cache[key].update(kwargs)
        _save()
        return dict(_cache[key])


async def add_warning(guild_id: int, user_id: int) -> int:
    async with _lock:
        key = str(guild_id)
        if key not in _cache:
            _cache[key] = json.loads(json.dumps(DEFAULT_GUILD_CONFIG))
        warnings = _cache[key].setdefault("warnings", {})
        warnings[str(user_id)] = warnings.get(str(user_id), 0) + 1
        _save()
        return warnings[str(user_id)]


async def get_warning_count(guild_id: int, user_id: int) -> int:
    async with _lock:
        key = str(guild_id)
        return _cache.get(key, {}).get("warnings", {}).get(str(user_id), 0)
