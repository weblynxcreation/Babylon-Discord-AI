"""
Automod: scans every message in a guild for banned words, invite-link spam,
mass mentions, and message-rate spam. Violations are tracked per-user so
repeat offenders get escalated automatically (delete -> warn -> timeout)
instead of every violation being treated the same.
"""
import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord

from . import store

# In-memory per-user recent message timestamps, for rate-limit detection.
# {(guild_id, user_id): deque[float]}
_message_times: dict = defaultdict(lambda: deque(maxlen=20))

# In-memory recent violation counts per user, reset after a period of good
# behavior. {(guild_id, user_id): int}
_violation_counts: dict = defaultdict(int)
_last_violation_time: dict = defaultdict(float)

VIOLATION_RESET_SECONDS = 60 * 30  # forgive violations after 30 clean minutes
TIMEOUT_AFTER_VIOLATIONS = 3
TIMEOUT_DURATION_SECONDS = 10 * 60

INVITE_RE = re.compile(r"(discord\.gg/|discordapp\.com/invite/|discord\.com/invite/)", re.IGNORECASE)


async def check_message(message: discord.Message) -> str | None:
    """Returns a short violation reason, or None if the message is clean."""
    if message.author.bot or not message.guild:
        return None

    config = await store.get_guild_config(message.guild.id)
    if not config["automod_enabled"]:
        return None

    content = message.content or ""
    lowered = content.lower()

    for word in config["banned_words"]:
        if word and word.lower() in lowered:
            return f"banned word (\"{word}\")"

    total_mentions = len(message.mentions) + len(message.role_mentions)
    if total_mentions > config["max_mentions"]:
        return f"mass mentions ({total_mentions} mentions)"

    if config["block_invite_links"] and INVITE_RE.search(content):
        return "unapproved Discord invite link"

    key = (message.guild.id, message.author.id)
    now = time.time()
    times = _message_times[key]
    times.append(now)
    recent = [t for t in times if now - t <= 10]
    if len(recent) > config["max_messages_per_10s"]:
        return f"message spam ({len(recent)} messages in 10s)"

    return None


async def handle_violation(message: discord.Message, reason: str, log_func) -> None:
    """Deletes the offending message and escalates based on recent history."""
    guild = message.guild
    member = message.author
    key = (guild.id, member.id)
    now = time.time()

    if now - _last_violation_time[key] > VIOLATION_RESET_SECONDS:
        _violation_counts[key] = 0
    _violation_counts[key] += 1
    _last_violation_time[key] = now
    count = _violation_counts[key]

    try:
        await message.delete()
    except discord.Forbidden:
        pass
    except discord.NotFound:
        pass

    if count >= TIMEOUT_AFTER_VIOLATIONS:
        try:
            until = discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION_SECONDS)
            await member.timeout(until, reason=f"Automod: repeated violations ({reason})")
            _violation_counts[key] = 0
            await log_func(
                guild,
                f"⏱️ Timed out {member.mention} for 10 minutes after {count} violations — latest: {reason}",
            )
            try:
                await member.send(
                    f"You've been timed out in **{guild.name}** for 10 minutes after repeated rule violations "
                    f"(latest: {reason})."
                )
            except discord.Forbidden:
                pass
            return
        except discord.Forbidden:
            pass  # bot lacks permission — fall through to a plain warning log

    await log_func(guild, f"🗑️ Deleted message from {member.mention} — {reason} (violation #{count})")
    try:
        await member.send(f"Your message in **{guild.name}** was removed: {reason}.")
    except discord.Forbidden:
        pass
