"""
Per-guild bot configuration, persisted to a local JSON file so settings
survive bot restarts. This covers server administration, moderation settings,
and warning counts. The file is written atomically to avoid leaving partial
JSON behind if the process stops during a save.
"""
import asyncio
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CONFIG_PATH = os.path.join(DATA_DIR, "moderation_config.json")

DEFAULT_GUILD_CONFIG = {
    "setup_complete": False,
    "admin_role_id": None,
    "market_channel_id": None,
    "market_alerts_enabled": False,
    "automod_enabled": True,
    "banned_words": [],
    "max_mentions": 5,
    "max_messages_per_10s": 6,
    "block_invite_links": True,
    "ai_automod_enabled": False,
    "ai_automod_min_chars": 12,
    "ai_automod_log_low_severity": True,
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


def _default_config() -> dict:
    """Return an independent copy so nested settings never leak between guilds."""
    return json.loads(json.dumps(DEFAULT_GUILD_CONFIG))


def _load() -> None:
    global _cache
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        _cache = {}
        return

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise ValueError(f"Guild configuration at {CONFIG_PATH} must contain a JSON object.")
    _cache = loaded


def _save() -> None:
    """Atomically replace the config file after the complete JSON is on disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    temporary_path = f"{CONFIG_PATH}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as f:
        json.dump(_cache, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary_path, CONFIG_PATH)


_load()


async def get_guild_config(guild_id: int) -> dict:
    async with _lock:
        key = str(guild_id)
        if key not in _cache:
            _cache[key] = _default_config()
            _save()

        # Backfill new defaults for guilds configured before an update.
        merged = _default_config()
        merged.update(_cache[key])
        return merged


async def update_guild_config(guild_id: int, **kwargs) -> dict:
    unknown = set(kwargs) - set(DEFAULT_GUILD_CONFIG)
    if unknown:
        raise ValueError(f"Unknown guild configuration keys: {', '.join(sorted(unknown))}")

    async with _lock:
        key = str(guild_id)
        if key not in _cache:
            _cache[key] = _default_config()
        _cache[key].update(kwargs)
        _save()

        merged = _default_config()
        merged.update(_cache[key])
        return merged


async def reset_guild_config(guild_id: int, *, preserve_warnings: bool = True) -> dict:
    """Reset one server without silently erasing its moderation warning history."""
    async with _lock:
        key = str(guild_id)
        warnings = {}
        if preserve_warnings:
            warnings = dict(_cache.get(key, {}).get("warnings", {}))

        _cache[key] = _default_config()
        _cache[key]["warnings"] = warnings
        _save()
        return _default_config() | {"warnings": warnings}


async def add_warning(guild_id: int, user_id: int) -> int:
    async with _lock:
        key = str(guild_id)
        if key not in _cache:
            _cache[key] = _default_config()
        warnings = _cache[key].setdefault("warnings", {})
        warnings[str(user_id)] = warnings.get(str(user_id), 0) + 1
        _save()
        return warnings[str(user_id)]


async def get_warning_count(guild_id: int, user_id: int) -> int:
    async with _lock:
        key = str(guild_id)
        return _cache.get(key, {}).get("warnings", {}).get(str(user_id), 0)
