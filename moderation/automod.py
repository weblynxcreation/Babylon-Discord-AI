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


def _register_violation(key: tuple) -> int:
    """Bumps (or resets-then-bumps) a user's violation count and returns the new count.
    Shared by keyword automod and AI moderation so both feed the same escalation ladder —
    three violations from either source (or a mix) trigger the same timeout."""
    now = time.time()
    if now - _last_violation_time[key] > VIOLATION_RESET_SECONDS:
        _violation_counts[key] = 0
    _violation_counts[key] += 1
    _last_violation_time[key] = now
    return _violation_counts[key]


async def apply_action(message: discord.Message, reason: str, log_func, force_timeout: bool = False) -> None:
    """Deletes the offending message and escalates based on recent history.

    force_timeout=True skips the violation-count ladder and times the member out
    immediately, regardless of prior history — used for severe single incidents
    (e.g. AI-flagged threats or self-harm content) where waiting for a third
    strike isn't appropriate.
    """
    guild = message.guild
    member = message.author
    key = (guild.id, member.id)
    count = _register_violation(key)

    try:
        await message.delete()
    except discord.Forbidden:
        pass
    except discord.NotFound:
        pass

    if force_timeout or count >= TIMEOUT_AFTER_VIOLATIONS:
        try:
            until = discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION_SECONDS)
            timeout_reason = reason if force_timeout else f"repeated violations ({reason})"
            await member.timeout(until, reason=f"Automod: {timeout_reason}")
            _violation_counts[key] = 0
            note = "severe violation" if force_timeout else f"{count} violations"
            await log_func(
                guild,
                f"⏱️ Timed out {member.mention} for 10 minutes ({note}) — latest: {reason}",
            )
            try:
                await member.send(
                    f"You've been timed out in **{guild.name}** for 10 minutes "
                    f"(reason: {reason})."
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


async def handle_violation(message: discord.Message, reason: str, log_func) -> None:
    """Keyword-automod entry point — thin wrapper around apply_action, kept as its
    own name so callers/log lines read naturally for rule-based violations."""
    await apply_action(message, reason, log_func)
