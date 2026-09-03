"""
Discord AI agent bot.

- Mention the bot or DM it to chat naturally (web search + reasoning).
- /image <prompt>  -> generates and posts an image
- /build <description> -> writes code/website files and sends a zip
- /ask <question>  -> one-off question, no channel history used
- Automod + raid protection run automatically in the background (see moderation/).
- /automod-*, /raid-*, /warn, /timeout, /kick, /ban, /purge, /modlog -> moderation controls

Run: python bot.py
"""
import os
import io
import logging
from datetime import timedelta

import discord
from discord import app_commands
from dotenv import load_dotenv

from agent import run_agent
from moderation import store as mod_store, automod, raid
from storage import chat_history

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discord-ai-agent")

DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "20"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # required for join events (raid protection) and member lookups

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DISCORD_FILE_SIZE_LIMIT = 8 * 1024 * 1024  # 8MB default (non-boosted) server limit


async def _send_agent_result(channel_or_interaction, result, followup: bool = False):
    """Send text, then any image/zip attachments produced by the agent turn."""
    files = []
    if result.image_bytes:
        files.append(discord.File(io.BytesIO(result.image_bytes), filename="generated.png"))
    if result.gif_bytes:
        files.append(discord.File(io.BytesIO(result.gif_bytes), filename="generated.gif"))
    if result.zip_path:
        size = os.path.getsize(result.zip_path)
        if size <= DISCORD_FILE_SIZE_LIMIT:
            files.append(discord.File(result.zip_path))
        else:
            result.text += f"\n\n⚠️ The generated project ({size // 1024}KB) is too large to attach here."

    content = result.text[:1900] if result.text else "Done."

    if followup:
        await channel_or_interaction.followup.send(content=content, files=files or discord.utils.MISSING)
    else:
        await channel_or_interaction.send(content=content, files=files or None)


async def _mod_log(guild: discord.Guild, text: str) -> None:
    """Posts a moderation event to the configured mod-log channel, if set."""
    config = await mod_store.get_guild_config(guild.id)
    channel_id = config.get("mod_log_channel_id")
    if not channel_id:
        log.info(f"[mod-log:{guild.name}] {text}")
        return
    channel = guild.get_channel(channel_id)
    if channel:
        try:
            await channel.send(text[:1900])
        except discord.Forbidden:
            log.warning(f"Missing permission to post in mod-log channel for {guild.name}")
    else:
        log.info(f"[mod-log:{guild.name}] {text}")


@client.event
async def on_ready():
    await tree.sync()
    log.info(f"Logged in as {client.user} (id={client.user.id})")


@client.event
async def on_member_join(member: discord.Member):
    await raid.handle_join(member, _mod_log)


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Automod runs on every guild message, independent of whether the bot
    # is mentioned — this is what actually catches spam/raids in real time.
    if message.guild:
        violation = await automod.check_message(message)
        if violation:
            await automod.handle_violation(message, violation, _mod_log)
            return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mention = client.user in message.mentions

    if not (is_dm or is_mention):
        return

    content = message.content
    if is_mention:
        content = content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()

    if not content:
        return

    async with message.channel.typing():
        history = await chat_history.get_history(message.channel.id, limit=HISTORY_LIMIT)
        try:
            result = await run_agent(history, content)
        except Exception as e:
            log.exception("Agent run failed")
            await message.channel.send(f"Something went wrong: `{e}`")
            return

        await chat_history.append_message(message.channel.id, "user", content, max_history=HISTORY_LIMIT)
        await chat_history.append_message(message.channel.id, "assistant", result.text, max_history=HISTORY_LIMIT)

        await _send_agent_result(message.channel, result)


@tree.command(name="ask", description="Ask the AI agent a one-off question (with live web search).")
@app_commands.describe(question="What do you want to ask?")
async def ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)
    try:
        result = await run_agent([], question)
    except Exception as e:
        log.exception("Agent run failed")
        await interaction.followup.send(f"Something went wrong: `{e}`")
        return
    await _send_agent_result(interaction, result, followup=True)


@tree.command(name="image", description="Generate an image from a text prompt.")
@app_commands.describe(prompt="Describe the image you want.")
async def image(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer(thinking=True)
    try:
        result = await run_agent([], f"Generate an image: {prompt}")
    except Exception as e:
        log.exception("Image generation failed")
        await interaction.followup.send(f"Something went wrong: `{e}`")
        return
    await _send_agent_result(interaction, result, followup=True)


@tree.command(name="gif", description="Generate a short animated GIF from a text prompt.")
@app_commands.describe(prompt="Describe the animation/scene you want.")
async def gif(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer(thinking=True)
    try:
        result = await run_agent([], f"Generate an animated GIF: {prompt}")
    except Exception as e:
        log.exception("GIF generation failed")
        await interaction.followup.send(f"Something went wrong: `{e}`")
        return
    await _send_agent_result(interaction, result, followup=True)


@tree.command(name="clearhistory", description="Forget the AI's conversation memory for this channel/DM.")
async def clearhistory(interaction: discord.Interaction):
    await chat_history.clear_history(interaction.channel_id)
    await interaction.response.send_message("Conversation history for this channel has been cleared.", ephemeral=True)


@tree.command(name="build", description="Generate code or a website and get it as a downloadable zip.")
@app_commands.describe(description="Describe what you want built.")
async def build(interaction: discord.Interaction, description: str):
    await interaction.response.defer(thinking=True)
    try:
        result = await run_agent(
            [],
            f"Build the following and package it with package_files: {description}",
        )
    except Exception as e:
        log.exception("Build failed")
        await interaction.followup.send(f"Something went wrong: `{e}`")
        return
    await _send_agent_result(interaction, result, followup=True)


# ---------------------------------------------------------------------------
# Moderation commands
# ---------------------------------------------------------------------------

automod_group = app_commands.Group(name="automod", description="Configure automatic message moderation.")
raid_group = app_commands.Group(name="raid", description="Configure raid protection.")


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You don't have permission to use this command.", ephemeral=True
        )
        return
    log.exception("Slash command error", exc_info=error)
    msg = f"Something went wrong: `{error}`"
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


@automod_group.command(name="toggle", description="Turn automod on or off for this server.")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_toggle(interaction: discord.Interaction, enabled: bool):
    await mod_store.update_guild_config(interaction.guild_id, automod_enabled=enabled)
    await interaction.response.send_message(f"Automod is now {'ON' if enabled else 'OFF'}.", ephemeral=True)


@automod_group.command(name="addword", description="Add a word/phrase to the banned list.")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_addword(interaction: discord.Interaction, word: str):
    config = await mod_store.get_guild_config(interaction.guild_id)
    words = config["banned_words"]
    if word.lower() not in [w.lower() for w in words]:
        words.append(word)
        await mod_store.update_guild_config(interaction.guild_id, banned_words=words)
    await interaction.response.send_message(f"Added `{word}` to the banned word list.", ephemeral=True)


@automod_group.command(name="removeword", description="Remove a word/phrase from the banned list.")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_removeword(interaction: discord.Interaction, word: str):
    config = await mod_store.get_guild_config(interaction.guild_id)
    words = [w for w in config["banned_words"] if w.lower() != word.lower()]
    await mod_store.update_guild_config(interaction.guild_id, banned_words=words)
    await interaction.response.send_message(f"Removed `{word}` from the banned word list.", ephemeral=True)


@automod_group.command(name="settings", description="Show current automod settings.")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_settings(interaction: discord.Interaction):
    config = await mod_store.get_guild_config(interaction.guild_id)
    words = ", ".join(config["banned_words"]) or "(none)"
    text = (
        f"**Automod**: {'ON' if config['automod_enabled'] else 'OFF'}\n"
        f"**Banned words**: {words}\n"
        f"**Max mentions/message**: {config['max_mentions']}\n"
        f"**Max messages/10s**: {config['max_messages_per_10s']}\n"
        f"**Block invite links**: {config['block_invite_links']}"
    )
    await interaction.response.send_message(text, ephemeral=True)


@raid_group.command(name="mode", description="Manually turn raid lockdown mode on or off.")
@app_commands.checks.has_permissions(manage_guild=True)
async def raid_mode(interaction: discord.Interaction, enabled: bool):
    await mod_store.update_guild_config(interaction.guild_id, raid_mode_active=enabled)
    await interaction.response.send_message(f"Raid mode is now {'ON' if enabled else 'OFF'}.", ephemeral=True)


@raid_group.command(name="config", description="Configure raid protection thresholds.")
@app_commands.describe(
    threshold="Number of joins that triggers raid mode",
    window_seconds="Time window (seconds) the threshold is measured over",
    min_account_age_hours="Accounts newer than this are actioned during raid mode",
    action="What to do to suspicious new joins during raid mode",
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="kick", value="kick"),
        app_commands.Choice(name="ban", value="ban"),
        app_commands.Choice(name="alert only (no action)", value="alert_only"),
    ]
)
@app_commands.checks.has_permissions(manage_guild=True)
async def raid_config(
    interaction: discord.Interaction,
    threshold: int = None,
    window_seconds: int = None,
    min_account_age_hours: int = None,
    action: app_commands.Choice[str] = None,
):
    updates = {}
    if threshold is not None:
        updates["raid_join_threshold"] = threshold
    if window_seconds is not None:
        updates["raid_join_window_seconds"] = window_seconds
    if min_account_age_hours is not None:
        updates["raid_min_account_age_hours"] = min_account_age_hours
    if action is not None:
        updates["raid_action"] = action.value

    config = await mod_store.update_guild_config(interaction.guild_id, **updates)
    text = (
        f"**Raid threshold**: {config['raid_join_threshold']} joins / {config['raid_join_window_seconds']}s\n"
        f"**Min account age**: {config['raid_min_account_age_hours']}h\n"
        f"**Action**: {config['raid_action']}"
    )
    await interaction.response.send_message(text, ephemeral=True)


tree.add_command(automod_group)
tree.add_command(raid_group)


@tree.command(name="modlog", description="Set the channel moderation events get logged to.")
@app_commands.checks.has_permissions(manage_guild=True)
async def modlog(interaction: discord.Interaction, channel: discord.TextChannel):
    await mod_store.update_guild_config(interaction.guild_id, mod_log_channel_id=channel.id)
    await interaction.response.send_message(f"Mod log set to {channel.mention}.", ephemeral=True)


@tree.command(name="warn", description="Warn a user (logged, DM'd, no other action taken).")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    count = await mod_store.add_warning(interaction.guild_id, member.id)
    await _mod_log(interaction.guild, f"⚠️ {interaction.user.mention} warned {member.mention} — {reason} (warning #{count})")
    try:
        await member.send(f"You were warned in **{interaction.guild.name}**: {reason}")
    except discord.Forbidden:
        pass
    await interaction.response.send_message(f"Warned {member.mention} (warning #{count}).", ephemeral=True)


@tree.command(name="timeout", description="Time out a user for a number of minutes.")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout_cmd(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason given"):
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    try:
        await member.timeout(until, reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to time out that user.", ephemeral=True)
        return
    await _mod_log(interaction.guild, f"⏱️ {interaction.user.mention} timed out {member.mention} for {minutes}m — {reason}")
    await interaction.response.send_message(f"Timed out {member.mention} for {minutes} minutes.", ephemeral=True)


@tree.command(name="kick", description="Kick a user from the server.")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
    try:
        await member.kick(reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to kick that user.", ephemeral=True)
        return
    await _mod_log(interaction.guild, f"👢 {interaction.user.mention} kicked {member.mention} — {reason}")
    await interaction.response.send_message(f"Kicked {member.mention}.", ephemeral=True)


@tree.command(name="ban", description="Ban a user from the server.")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
    try:
        await member.ban(reason=reason, delete_message_seconds=0)
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to ban that user.", ephemeral=True)
        return
    await _mod_log(interaction.guild, f"🔨 {interaction.user.mention} banned {member.mention} — {reason}")
    await interaction.response.send_message(f"Banned {member.mention}.", ephemeral=True)


@tree.command(name="purge", description="Delete a number of recent messages in this channel.")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, count: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=count)
    await _mod_log(interaction.guild, f"🧹 {interaction.user.mention} purged {len(deleted)} messages in {interaction.channel.mention}")
    await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
