"""
Raid protection: watches member joins for a suspicious burst (many joins in
a short window — a classic raid pattern). Once triggered, raid mode screens
every further join against a minimum account age and kicks/bans/alerts on
anything too new, until a moderator clears it with /raidmode off.
"""
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import discord

from . import store

# {guild_id: deque[float]}
_join_times: dict = defaultdict(lambda: deque(maxlen=100))


async def handle_join(member: discord.Member, log_func) -> None:
    guild = member.guild
    config = await store.get_guild_config(guild.id)

    if not config["raid_protection_enabled"]:
        return

    now = time.time()
    times = _join_times[guild.id]
    times.append(now)
    window = config["raid_join_window_seconds"]
    recent = [t for t in times if now - t <= window]

    account_age_hours = (datetime.now(timezone.utc) - member.created_at).total_seconds() / 3600

    if len(recent) >= config["raid_join_threshold"] and not config["raid_mode_active"]:
        await store.update_guild_config(guild.id, raid_mode_active=True)
        await log_func(
            guild,
            f"🚨 **Raid detected**: {len(recent)} joins in {window}s. Raid mode is now ON "
            f"(action: `{config['raid_action']}`, min account age: {config['raid_min_account_age_hours']}h). "
            f"Run `/raidmode off` once things settle.",
        )

    if config["raid_mode_active"] and account_age_hours < config["raid_min_account_age_hours"]:
        action = config["raid_action"]
        reason = (
            f"Raid protection: account created {account_age_hours:.1f}h ago "
            f"(minimum {config['raid_min_account_age_hours']}h required during raid mode)"
        )
        try:
            if action == "kick":
                await member.kick(reason=reason)
                await log_func(guild, f"👢 Kicked {member} (`{member.id}`) — {reason}")
            elif action == "ban":
                await member.ban(reason=reason, delete_message_seconds=0)
                await log_func(guild, f"🔨 Banned {member} (`{member.id}`) — {reason}")
            else:
                await log_func(
                    guild,
                    f"⚠️ New join during raid mode (alert only, no action taken): "
                    f"{member} (`{member.id}`) — {reason}",
                )
        except discord.Forbidden:
            await log_func(guild, f"⚠️ Raid protection couldn't act on {member} — bot is missing permissions.")
