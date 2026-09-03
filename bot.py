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
import json
import logging
import math
import re
from datetime import timedelta

import discord
from discord import app_commands
from dotenv import load_dotenv

from agent import run_agent
from moderation import store as mod_store, automod, ai_mod, raid
from storage import chat_history
from tools.capital_rift import capital_rift_wiki
from babylon_market import (
    BabylonAPIError,
    BabylonMarketClient,
    calculate_market_status,
    company_suggestions,
    find_company,
    format_currency,
    format_percent,
    rank_companies,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discord-ai-agent")

DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "20"))
BABYLON_API_BASE = os.environ.get("BABYLON_API_BASE", "https://holdings.thebabylon.hu/api/v1")
BABYLON_SITE_BASE = os.environ.get("BABYLON_SITE_BASE", "https://holdings.thebabylon.hu").rstrip("/")
BABYLON_CACHE_SECONDS = float(os.environ.get("BABYLON_CACHE_SECONDS", "30"))
BABYLON_FRESH_AFTER_MINUTES = int(os.environ.get("BABYLON_FRESH_AFTER_MINUTES", "60"))
BABYLON_OUTDATED_AFTER_HOURS = int(os.environ.get("BABYLON_OUTDATED_AFTER_HOURS", "24"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # required for join events (raid protection) and member lookups

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
market_client = BabylonMarketClient(
    BABYLON_API_BASE,
    timeout_seconds=float(os.environ.get("BABYLON_HTTP_TIMEOUT_SECONDS", "10")),
    cache_seconds=BABYLON_CACHE_SECONDS,
)

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
    if DISCORD_GUILD_ID:
        try:
            development_guild = discord.Object(id=int(DISCORD_GUILD_ID))
        except ValueError:
            raise RuntimeError("DISCORD_GUILD_ID must be a numeric Discord server ID.")
        tree.copy_global_to(guild=development_guild)
        synced = await tree.sync(guild=development_guild)
        log.info(
            "Synced %s slash commands to development guild %s",
            len(synced),
            DISCORD_GUILD_ID,
        )
    else:
        synced = await tree.sync()
        log.info("Synced %s global slash commands", len(synced))
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

        # AI-powered moderation: catches harassment/hate/threats/self-harm talk
        # that doesn't contain any literal banned word. Opt-in per server
        # (/automod ai-toggle) since it costs an extra LLM call per message checked.
        mod_config = await mod_store.get_guild_config(message.guild.id)
        if mod_config.get("ai_automod_enabled") and ai_mod.should_check(
            message.content or "", mod_config.get("ai_automod_min_chars", 12)
        ):
            ai_result = await ai_mod.classify_message(message.content)
            if ai_result["severity"] != "none":
                await ai_mod.handle_result(
                    message, ai_result, _mod_log, mod_config.get("ai_automod_log_low_severity", True)
                )
            if ai_result["severity"] in ("medium", "high"):
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


# ---------------------------------------------------------------------------
# Babylon Stock Market commands (public, read-only)
# ---------------------------------------------------------------------------

async def _market_companies(interaction: discord.Interaction):
    try:
        return await market_client.get_companies()
    except BabylonAPIError as exc:
        log.warning("Babylon market request failed: %s", exc)
        await interaction.followup.send(f"Market data is unavailable: {exc}", ephemeral=True)
        return None


def _company_url(company_id: str) -> str:
    return f"{BABYLON_SITE_BASE}/companies/{company_id}"


@tree.command(name="market", description="Show a live overview of the Babylon Stock Market.")
async def market(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    companies = await _market_companies(interaction)
    if companies is None:
        return
    if not companies:
        await interaction.followup.send("The Babylon market currently has no listed companies.")
        return

    leaders = rank_companies(companies, "value")[:5]
    total_cap = sum(company.total_value for company in companies)
    verified = sum(company.verified for company in companies)
    lines = [
        f"**{index}. [{company.name}]({_company_url(company.id)})** — "
        f"{format_currency(company.total_value)} · {format_percent(company.trend_pct)}"
        for index, company in enumerate(leaders, start=1)
    ]
    embed = discord.Embed(
        title="Babylon Stock Market",
        url=BABYLON_SITE_BASE,
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    embed.add_field(name="Listed companies", value=f"{len(companies):,}")
    embed.add_field(name="Combined value", value=format_currency(total_cap))
    embed.add_field(name="Verified", value=f"{verified:,}/{len(companies):,}")
    embed.set_footer(text=f"Public market data · cached for up to {BABYLON_CACHE_SECONDS:g} seconds")
    await interaction.followup.send(embed=embed)


@tree.command(name="stock", description="Look up a company on the Babylon Stock Market.")
@app_commands.describe(company="Company name")
async def stock(interaction: discord.Interaction, company: str):
    await interaction.response.defer(thinking=True)
    companies = await _market_companies(interaction)
    if companies is None:
        return
    match = find_company(companies, company)
    if match is None:
        await interaction.followup.send(
            f"I couldn't find a listed company matching `{company[:100]}`.", ephemeral=True
        )
        return

    color = discord.Color.green() if match.trend_pct >= 0 else discord.Color.red()
    embed = discord.Embed(
        title=match.name,
        url=_company_url(match.id),
        description="Verified Capital Rift company" if match.verified else "Unverified company",
        color=color,
    )
    embed.add_field(name="Share price", value=format_currency(match.share_price))
    embed.add_field(name="Trend", value=format_percent(match.trend_pct))
    embed.add_field(name="Total value", value=format_currency(match.total_value))
    embed.add_field(name="Net worth", value=format_currency(match.net_worth))
    embed.add_field(name="Profit/min", value=format_currency(match.profit_per_min))
    embed.add_field(name="Funded capital", value=format_currency(match.funded_capital))
    if match.last_synced_at:
        embed.add_field(
            name="Last synchronized",
            value=f"<t:{int(match.last_synced_at.timestamp())}:R>",
            inline=False,
        )
    await interaction.followup.send(embed=embed)


@stock.autocomplete("company")
async def stock_autocomplete(
    _interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    try:
        companies = await market_client.get_companies()
    except BabylonAPIError:
        return []
    return [
        app_commands.Choice(name=company.name[:100], value=company.name[:100])
        for company in company_suggestions(companies, current)
    ]


@tree.command(name="leaders", description="Rank Babylon companies by market value, price, or profit.")
@app_commands.describe(metric="Ranking metric", limit="Number of companies to show")
@app_commands.choices(
    metric=[
        app_commands.Choice(name="Total value", value="value"),
        app_commands.Choice(name="Share price", value="price"),
        app_commands.Choice(name="Profit per minute", value="profit"),
    ]
)
async def leaders(
    interaction: discord.Interaction,
    metric: app_commands.Choice[str],
    limit: app_commands.Range[int, 3, 10] = 5,
):
    await interaction.response.defer(thinking=True)
    companies = await _market_companies(interaction)
    if companies is None:
        return
    ranked = rank_companies(companies, metric.value)[:limit]
    value_for = {
        "value": lambda item: item.total_value,
        "price": lambda item: item.share_price,
        "profit": lambda item: item.profit_per_min,
    }[metric.value]
    lines = [
        f"**{index}. [{company.name}]({_company_url(company.id)})** — "
        f"{format_currency(value_for(company))}"
        for index, company in enumerate(ranked, start=1)
    ]
    embed = discord.Embed(
        title=f"Market leaders · {metric.name}",
        description="\n".join(lines) or "No companies are currently listed.",
        color=discord.Color.gold(),
    )
    await interaction.followup.send(embed=embed)


@tree.command(name="movers", description="Show the Babylon market's biggest gains and losses.")
@app_commands.describe(limit="Number of gainers and losers to show")
async def movers(
    interaction: discord.Interaction,
    limit: app_commands.Range[int, 1, 10] = 5,
):
    await interaction.response.defer(thinking=True)
    companies = await _market_companies(interaction)
    if companies is None:
        return
    gainers = sorted(
        (company for company in companies if company.trend_pct > 0),
        key=lambda company: company.trend_pct,
        reverse=True,
    )[:limit]
    losers = sorted(
        (company for company in companies if company.trend_pct < 0),
        key=lambda company: company.trend_pct,
    )[:limit]

    def mover_lines(items):
        return "\n".join(
            f"[{company.name}]({_company_url(company.id)}) — {format_percent(company.trend_pct)}"
            for company in items
        ) or "None"

    embed = discord.Embed(title="Market movers", color=discord.Color.gold())
    embed.add_field(name="Gainers", value=mover_lines(gainers), inline=False)
    embed.add_field(name="Losers", value=mover_lines(losers), inline=False)
    await interaction.followup.send(embed=embed)


@tree.command(name="market-status", description="Check verification and synchronization health.")
async def market_status(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    companies = await _market_companies(interaction)
    if companies is None:
        return
    status = calculate_market_status(
        companies,
        fresh_after=timedelta(minutes=BABYLON_FRESH_AFTER_MINUTES),
        outdated_after=timedelta(hours=BABYLON_OUTDATED_AFTER_HOURS),
    )
    healthy = (
        status.total > 0
        and status.verified == status.total
        and status.outdated == 0
        and status.missing_sync_time == 0
    )
    embed = discord.Embed(
        title="Babylon market status",
        description=(
            "Market API online. All listed company snapshots are current."
            if healthy
            else "Market API online. Some company snapshots have not recently refreshed."
        ),
        color=discord.Color.green() if healthy else discord.Color.orange(),
    )
    embed.add_field(name="Verified", value=f"{status.verified:,}/{status.total:,}")
    embed.add_field(
        name=f"Fresh (≤{BABYLON_FRESH_AFTER_MINUTES}m)", value=f"{status.fresh:,}"
    )
    embed.add_field(
        name=f"Delayed (≤{BABYLON_OUTDATED_AFTER_HOURS}h)", value=f"{status.delayed:,}"
    )
    embed.add_field(
        name=f"Outdated (>{BABYLON_OUTDATED_AFTER_HOURS}h)", value=f"{status.outdated:,}"
    )
    embed.add_field(name="Missing sync time", value=f"{status.missing_sync_time:,}")
    if status.newest_sync:
        embed.add_field(
            name="Newest synchronization",
            value=f"<t:{int(status.newest_sync.timestamp())}:R>",
            inline=False,
        )
    if status.oldest_sync:
        embed.add_field(
            name="Oldest synchronization",
            value=f"<t:{int(status.oldest_sync.timestamp())}:R>",
            inline=False,
        )
    await interaction.followup.send(embed=embed)


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
config_group = app_commands.Group(name="config", description="View or change this server's bot settings.")


async def _is_bot_admin(interaction: discord.Interaction) -> bool:
    """Allow server managers plus members of the configured bot-admin role."""
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        return False

    permissions = interaction.user.guild_permissions
    if permissions.administrator or permissions.manage_guild:
        return True

    config = await mod_store.get_guild_config(interaction.guild.id)
    admin_role_id = config.get("admin_role_id")
    return bool(
        admin_role_id
        and any(role.id == admin_role_id for role in interaction.user.roles)
    )


def bot_admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if await _is_bot_admin(interaction):
            return True
        raise app_commands.CheckFailure(
            "This command requires Manage Server or the configured bot-admin role."
        )

    return app_commands.check(predicate)


def _configuration_embed(guild: discord.Guild, config: dict) -> discord.Embed:
    admin_role = guild.get_role(config.get("admin_role_id") or 0)
    market_channel = guild.get_channel(config.get("market_channel_id") or 0)
    mod_log_channel = guild.get_channel(config.get("mod_log_channel_id") or 0)

    embed = discord.Embed(
        title="Babylon bot configuration",
        description=(
            "Initial setup is complete."
            if config.get("setup_complete")
            else "Initial setup has not been completed."
        ),
        color=discord.Color.gold(),
    )
    embed.add_field(
        name="Bot administrators",
        value=admin_role.mention if admin_role else "Members with Manage Server",
        inline=False,
    )
    embed.add_field(
        name="Market channel",
        value=market_channel.mention if market_channel else "Not configured",
    )
    embed.add_field(
        name="Market alerts",
        value="Enabled" if config.get("market_alerts_enabled") else "Disabled",
    )
    embed.add_field(
        name="Moderation log",
        value=mod_log_channel.mention if mod_log_channel else "Not configured",
        inline=False,
    )
    return embed


@tree.command(name="setup", description="Configure the Babylon bot for this server.")
@app_commands.describe(
    admin_role="Role allowed to manage bot settings",
    market_channel="Channel for Babylon market updates",
    mod_log_channel="Channel for private moderation events",
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def setup(
    interaction: discord.Interaction,
    admin_role: discord.Role | None = None,
    market_channel: discord.TextChannel | None = None,
    mod_log_channel: discord.TextChannel | None = None,
):
    updates = {"setup_complete": True}
    if admin_role is not None:
        updates["admin_role_id"] = admin_role.id
    if market_channel is not None:
        updates["market_channel_id"] = market_channel.id
    elif isinstance(interaction.channel, discord.TextChannel):
        updates["market_channel_id"] = interaction.channel.id
    if mod_log_channel is not None:
        updates["mod_log_channel_id"] = mod_log_channel.id

    config = await mod_store.update_guild_config(interaction.guild_id, **updates)
    await interaction.response.send_message(
        embed=_configuration_embed(interaction.guild, config),
        ephemeral=True,
    )


@config_group.command(name="view", description="Show this server's current bot settings.")
@app_commands.guild_only()
@bot_admin_only()
async def config_view(interaction: discord.Interaction):
    config = await mod_store.get_guild_config(interaction.guild_id)
    await interaction.response.send_message(
        embed=_configuration_embed(interaction.guild, config),
        ephemeral=True,
    )


@config_group.command(name="admin-role", description="Choose the role that can manage bot settings.")
@app_commands.guild_only()
@bot_admin_only()
async def config_admin_role(interaction: discord.Interaction, role: discord.Role):
    config = await mod_store.update_guild_config(
        interaction.guild_id, admin_role_id=role.id, setup_complete=True
    )
    await interaction.response.send_message(
        embed=_configuration_embed(interaction.guild, config),
        ephemeral=True,
    )


@config_group.command(name="market-channel", description="Choose the channel for market updates.")
@app_commands.guild_only()
@bot_admin_only()
async def config_market_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
    config = await mod_store.update_guild_config(
        interaction.guild_id, market_channel_id=channel.id, setup_complete=True
    )
    await interaction.response.send_message(
        embed=_configuration_embed(interaction.guild, config),
        ephemeral=True,
    )


@config_group.command(name="alerts", description="Enable or disable automated market alerts.")
@app_commands.guild_only()
@bot_admin_only()
async def config_alerts(interaction: discord.Interaction, enabled: bool):
    config = await mod_store.update_guild_config(
        interaction.guild_id, market_alerts_enabled=enabled
    )
    await interaction.response.send_message(
        embed=_configuration_embed(interaction.guild, config),
        ephemeral=True,
    )


@config_group.command(name="reset", description="Reset bot settings but keep moderation warnings.")
@app_commands.describe(confirm="Must be true to confirm the reset")
@app_commands.guild_only()
@bot_admin_only()
async def config_reset(interaction: discord.Interaction, confirm: bool):
    if not confirm:
        await interaction.response.send_message(
            "Nothing was reset. Run the command with confirm set to True to continue.",
            ephemeral=True,
        )
        return

    config = await mod_store.reset_guild_config(
        interaction.guild_id, preserve_warnings=True
    )
    await interaction.response.send_message(
        content="Server bot settings were reset. Moderation warning history was preserved.",
        embed=_configuration_embed(interaction.guild, config),
        ephemeral=True,
    )


@tree.command(name="wiki-status", description="Check the local Capital Rift wiki index.")
@app_commands.guild_only()
@bot_admin_only()
async def wiki_status(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    payload = json.loads(await capital_rift_wiki("status"))
    data = payload.get("data", {})
    error = data.get("error")
    if error:
        await interaction.followup.send(
            f"Capital Rift wiki is not ready: {error}", ephemeral=True
        )
        return

    await interaction.followup.send(
        (
            "**Capital Rift wiki**\n"
            f"Indexed notes: **{data.get('totalNotes', 0):,}**\n"
            "Vault access: **read-only**"
        ),
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Capital Rift direct wiki commands (no AI tool-calling required)
# ---------------------------------------------------------------------------

def _wiki_embed(title: str, note: dict, *, color: discord.Color) -> discord.Embed:
    """Render a vault note safely inside Discord's embed limits."""
    source = note.get("path", "Unknown wiki note")
    body = (note.get("content") or "").strip()
    if len(body) > 3900:
        body = body[:3897].rstrip() + "…"
    embed = discord.Embed(
        title=title[:256],
        description=body or "This wiki note has no readable content.",
        color=color,
    )
    embed.set_footer(text=f"Capital Rift wiki · Source: {source}")
    return embed


async def _capital_rift_note(query: str, kind: str) -> tuple[dict | None, str | None]:
    """Search then read the strongest local-wiki match for a typed lookup."""
    payload = json.loads(await capital_rift_wiki("search", query=f"{query} {kind}", limit=5))
    data = payload.get("data", {})
    if data.get("error"):
        return None, data["error"]
    results = data.get("results") or []
    if not results:
        return None, f"No {kind} matching '{query[:100]}' was found in the Capital Rift wiki."

    normalized_query = query.casefold().strip()
    result = next(
        (
            item for item in results
            if item.get("title", "").casefold().strip() == normalized_query
            or item.get("path", "").rsplit("/", 1)[-1].removesuffix(".md").casefold() == normalized_query
        ),
        results[0],
    )
    payload = json.loads(await capital_rift_wiki("read", note_path=result["path"]))
    data = payload.get("data", {})
    if data.get("error"):
        return None, data["error"]
    return data, None


def _per_minute_rate(note: str) -> float | None:
    """Read an explicit output/recipe rate from common wiki Markdown formats."""
    patterns = (
        r"(?:recipe|output|production)\s*rate\s*[:|]\s*[* ]*([0-9]+(?:\.[0-9]+)?)\s*(?:/|\bper\s+)m(?:in(?:ute)?)?\b",
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:/|\bper\s+)m(?:in(?:ute)?)?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, note, flags=re.IGNORECASE)
        if match:
            rate = float(match.group(1))
            if rate > 0:
                return rate
    return None


def _machine_name(note: str) -> str | None:
    match = re.search(
        r"(?:machine|building|produced\s+by)\s*[:|]\s*[* ]*([^\n|*]+)",
        note,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip(" .:-") if match else None


@tree.command(name="item", description="Look up a Capital Rift item in the local wiki.")
@app_commands.describe(name="Item name, for example Iron Plate")
async def item_lookup(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True)
    note, error = await _capital_rift_note(name, "item")
    if error:
        await interaction.followup.send(error, ephemeral=True)
        return
    await interaction.followup.send(
        embed=_wiki_embed(f"Item · {note.get('title', name)}", note, color=discord.Color.blue())
    )


@tree.command(name="recipe", description="Look up a Capital Rift recipe in the local wiki.")
@app_commands.describe(name="Recipe or output item name, for example Iron Plate")
async def recipe_lookup(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True)
    note, error = await _capital_rift_note(name, "recipe")
    if error:
        await interaction.followup.send(error, ephemeral=True)
        return
    await interaction.followup.send(
        embed=_wiki_embed(f"Recipe · {note.get('title', name)}", note, color=discord.Color.orange())
    )


@tree.command(name="machine", description="Look up a Capital Rift production machine in the local wiki.")
@app_commands.describe(name="Machine name, for example Furnace")
async def machine_lookup(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True)
    note, error = await _capital_rift_note(name, "machine")
    if error:
        await interaction.followup.send(error, ephemeral=True)
        return
    await interaction.followup.send(
        embed=_wiki_embed(f"Machine · {note.get('title', name)}", note, color=discord.Color.purple())
    )


@tree.command(name="production", description="Calculate machines required for a Capital Rift output target.")
@app_commands.describe(
    item="Output item or recipe name, for example Iron Plate",
    target_per_minute="Desired output per minute",
)
async def production(interaction: discord.Interaction, item: str, target_per_minute: app_commands.Range[float, 0.001, 1000000]):
    await interaction.response.defer(thinking=True)
    note, error = await _capital_rift_note(item, "recipe")
    if error:
        await interaction.followup.send(error, ephemeral=True)
        return

    rate = _per_minute_rate(note.get("content", ""))
    if rate is None:
        await interaction.followup.send(
            "I found the recipe, but its wiki note does not contain an explicit per-minute output rate, "
            f"so I will not guess the machine count. Source: {note.get('path', 'unknown')}",
            ephemeral=True,
        )
        return

    machines = int(math.ceil(float(target_per_minute) / rate))
    machine = _machine_name(note.get("content", "")) or "the recipe machine"
    actual_output = machines * rate
    embed = discord.Embed(
        title=f"Production plan · {note.get('title', item)}",
        description=(
            f"Target: **{float(target_per_minute):g}/min**\n"
            f"Recipe rate: **{rate:g}/min per machine**\n"
            f"Machines needed: **{machines:,} {machine}**\n"
            f"Output at full capacity: **{actual_output:g}/min**"
        ),
        color=discord.Color.green(),
    )
    embed.set_footer(text=f"Capital Rift wiki · Source: {note.get('path', 'unknown')}")
    await interaction.followup.send(embed=embed)


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        message = str(error) or "You don't have permission to use this command."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
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
        f"**Block invite links**: {config['block_invite_links']}\n"
        f"**AI moderation**: {'ON' if config['ai_automod_enabled'] else 'OFF'}"
        f" (min {config['ai_automod_min_chars']} chars, log low-severity: {config['ai_automod_log_low_severity']})"
    )
    await interaction.response.send_message(text, ephemeral=True)


@automod_group.command(
    name="ai-toggle",
    description="Turn AI-powered moderation on/off (catches harassment/hate/threats without exact banned words).",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_ai_toggle(interaction: discord.Interaction, enabled: bool):
    await mod_store.update_guild_config(interaction.guild_id, ai_automod_enabled=enabled)
    await interaction.response.send_message(
        f"AI-powered moderation is now {'ON' if enabled else 'OFF'}.\n"
        + ("It runs on every message that passes keyword automod and is at least the configured "
           "minimum length — use `/automod ai-settings` to tune that." if enabled else ""),
        ephemeral=True,
    )


@automod_group.command(
    name="ai-settings",
    description="Configure AI moderation sensitivity.",
)
@app_commands.describe(
    min_chars="Skip messages shorter than this (saves API calls on trivial chat).",
    log_low_severity="Post a quiet mod-log entry for low-severity flags even though no action is taken.",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_ai_settings(
    interaction: discord.Interaction,
    min_chars: int = None,
    log_low_severity: bool = None,
):
    updates = {}
    if min_chars is not None:
        updates["ai_automod_min_chars"] = max(1, min_chars)
    if log_low_severity is not None:
        updates["ai_automod_log_low_severity"] = log_low_severity

    config = await mod_store.update_guild_config(interaction.guild_id, **updates)
    text = (
        f"**AI moderation**: {'ON' if config['ai_automod_enabled'] else 'OFF'}\n"
        f"**Min message length checked**: {config['ai_automod_min_chars']} chars\n"
        f"**Log low-severity flags**: {config['ai_automod_log_low_severity']}\n\n"
        f"Severity → action: none = ignore, low = log only, medium = delete + counts toward "
        f"the 3-strike timeout, high = delete + immediate 10-minute timeout."
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
tree.add_command(config_group)


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
