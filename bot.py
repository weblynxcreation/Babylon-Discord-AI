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
import asyncio
import io
import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from agent import AgentResult, run_agent
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

from response_cards import GREEN, ORANGE, send_card, send_production_card
from card_primitives import add_actions, build_card
from wiki_cards import linked_wiki_card
from response_cards import send_factory_plan
from tools.factory_calculator import FactoryRequest, FactoryError, full_factory_request, parse_factory_request, parse_recipe, plan_factory
from knowledge.obsidian_vault import VaultError
from reliability import timeout_seconds
from observability import current_trace, mark_delivery, mark_status, trace_event, diagnostic_excerpt, configure_logging
from response_lifecycle import bounded_command, bounded_message, typing_scope, recover_response

if __name__ == "__main__" and not logging.getLogger().handlers:
    configure_logging(Path(__file__).resolve().parent / "logs")
else:
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


class TimeoutLogView(discord.ui.View):
    """One-click, redacted diagnostic delivery for a timed-out request."""
    def __init__(self, source, turn_id=None):
        super().__init__(timeout=300)
        self.source = source
        self.turn_id = turn_id

    @discord.ui.button(label="Send logs", style=discord.ButtonStyle.secondary, emoji="📄")
    async def send_logs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await asyncio.wait_for(self._send_diagnostics(interaction), timeout=15)
        except asyncio.CancelledError:
            await recover_response(interaction, "Diagnostic request cancelled. Please try again.", interaction=True)
            raise
        except Exception:
            await recover_response(interaction, "I could not send diagnostics. Please try again.", interaction=True)

    async def _send_diagnostics(self, interaction):
        guild = getattr(interaction, "guild", None)
        target = None
        if guild is not None:
            config = await mod_store.get_guild_config(guild.id)
            target = guild.get_channel(config.get("mod_log_channel_id") or 0)
        if target is None:
            await interaction.followup.send("No diagnostic log channel is configured.", ephemeral=True)
            return
        text = await asyncio.to_thread(diagnostic_excerpt, Path("logs/local-bot.log"), self.turn_id)
        payload = io.BytesIO(text.encode("utf-8"))
        file = discord.File(payload, filename="babylon-timeout-log.txt")
        try:
            await target.send(content="Request diagnostics" + (f" · {self.turn_id}" if self.turn_id else ""),
                              file=file, allowed_mentions=discord.AllowedMentions.none())
            await interaction.followup.send(f"Diagnostics sent to {target.mention}.", ephemeral=True,
                                            allowed_mentions=discord.AllowedMentions.none())
        finally:
            file.close()


async def _send_agent_result(channel_or_interaction, result, followup: bool = False, *, card: bool = False, factory: bool = False, factory_name: str = "Factory setup"):
    """Deliver conversational text or structured cards and record terminal status."""
    mark_status(result.status)
    trace = current_trace.get()
    if not getattr(result, "turn_id", "") and trace:
        result.turn_id = trace.turn_id
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

    destination = channel_or_interaction.followup.send if followup else channel_or_interaction.send
    async def send(**kwargs):
        sent = await destination(**kwargs)
        mark_delivery()
        return sent
    try:
        if result.status == "timeout":
            # Conversational timeout stays plain text with a classic diagnostics button.
            await send(
                content=(result.text or "The request ran out of time.")[:1900],
                view=TimeoutLogView(channel_or_interaction, getattr(result, "turn_id", None)),
                allowed_mentions=discord.AllowedMentions.none(),
                files=files,
            )
            return
        if getattr(result, "factory_plan", None) is not None and result.status == "completed":
            await send_factory_plan(send, result.factory_plan)
            return
        if card and factory and result.status == "completed":
            await send_production_card(
                send, factory_name,
                result.text or "No verified factory details were found.",
                wiki_context=getattr(result, "wiki_context", ""),
            )
            return
        if card and result.status == "completed":
            # Structured media results (/image, /gif, /build): card with attachments.
            await send_card(send, "Babylon Helper", result.text or "Done.", files=files)
            return
        # Conversational replies stay plain text; deliver the full answer in
        # <=1900-character chunks instead of truncating it.
        text = result.text or "Done."
        chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)]
        for index, chunk in enumerate(chunks):
            await send(
                content=chunk if chunk.strip() else "\u200b",
                allowed_mentions=discord.AllowedMentions.none(),
                files=files if index == 0 else [],
            )
    finally:
        for file in files:
            file.close()


async def _mod_log(guild: discord.Guild, text: str) -> None:
    """Posts a moderation event to the configured mod-log channel, if set."""
    config = await mod_store.get_guild_config(guild.id)
    channel_id = config.get("mod_log_channel_id")
    if not channel_id:
        log.info("Moderation event: no diagnostic channel configured")
        return
    channel = guild.get_channel(channel_id)
    if channel:
        try:
            await channel.send(text[:1900])
        except discord.Forbidden:
            log.warning(f"Missing permission to post in mod-log channel for {guild.name}")
    else:
        log.info("Moderation event: no diagnostic channel configured")


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
    await _maybe_send_policy_card(member)


# ---------------------------------------------------------------------------
# Onboarding policy acceptance (#9)
# ---------------------------------------------------------------------------

POLICY_ACCEPT_CUSTOM_ID = "policy:accept:{guild_id}"


def _build_policy_card(config: dict, guild_id: int):
    """Acceptance card with links to the live policy pages and one button."""
    body = (
        "Welcome to Babylon Holdings! Before you get full access, please review our community policies:\n\n"
        f"- [Privacy Policy]({config.get('policy_privacy_url')})\n"
        f"- [Terms of Service]({config.get('policy_terms_url')})\n\n"
        "Press **I accept** below once you have read both. Your acceptance is "
        "recorded with a timestamp and can be reviewed by server staff."
    )
    view = build_card(
        "Community policies", body, state="info",
        footer="Acceptance is required for full member access",
    )
    accept = discord.ui.Button(
        label="I accept", style=discord.ButtonStyle.success,
        custom_id=POLICY_ACCEPT_CUSTOM_ID.format(guild_id=guild_id),
    )
    return add_actions(view, accept)


async def _maybe_send_policy_card(member: discord.Member) -> None:
    """DM the acceptance card on join when enabled and not yet accepted."""
    try:
        config = await mod_store.get_guild_config(member.guild.id)
    except Exception:
        log.exception("Policy config lookup failed for guild %s", member.guild.id)
        return
    if not config.get("policy_enabled") or str(member.id) in config.get("policy_acceptances", {}):
        return
    try:
        await member.send(view=_build_policy_card(config, member.guild.id))
    except discord.HTTPException:
        # Closed DMs are expected; staff can re-send via /policy resend.
        log.info("[policy:%s] Could not DM acceptance card to %s", member.guild.id, member.id)


async def record_policy_acceptance(guild_id: int, user_id: int, *, via: str) -> str:
    """Store the first acceptance (idempotent) and return its ISO timestamp."""
    config = await mod_store.get_guild_config(guild_id)
    acceptances = dict(config.get("policy_acceptances", {}))
    key = str(user_id)
    if key not in acceptances:
        acceptances[key] = {"accepted_at": datetime.now(timezone.utc).isoformat(), "via": via}
        await mod_store.update_guild_config(guild_id, policy_acceptances=acceptances)
    return acceptances[key]["accepted_at"]


@client.event
async def on_interaction(interaction: discord.Interaction):
    """Component dispatch that survives restarts (no persistent-view registry)."""
    custom_id = getattr(interaction.data, "get", lambda *_: None)("custom_id") if interaction.data else None
    if interaction.type != discord.InteractionType.component or not custom_id:
        return
    if not custom_id.startswith("policy:accept:"):
        return
    try:
        guild_id = int(custom_id.rsplit(":", 1)[1])
    except ValueError:
        return
    accepted_at = await record_policy_acceptance(guild_id, interaction.user.id, via="dm-button")
    await interaction.response.send_message(
        f"Accepted ✓ — recorded <t:{int(datetime.fromisoformat(accepted_at).timestamp())}:f>. "
        "Welcome aboard! Staff can verify this anytime.",
        ephemeral=True,
    )


policy_group = app_commands.Group(
    name="policy",
    description="Configure new-member policy acceptance.",
)


@policy_group.command(name="enable", description="Require policy acceptance for new members.")
@app_commands.describe(privacy_url="Privacy policy page", terms_url="Terms of service page")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
@bounded_command
async def policy_enable(
    interaction: discord.Interaction,
    privacy_url: str | None = None,
    terms_url: str | None = None,
):
    updates = {"policy_enabled": True}
    if privacy_url:
        updates["policy_privacy_url"] = privacy_url
    if terms_url:
        updates["policy_terms_url"] = terms_url
    config = await mod_store.update_guild_config(interaction.guild_id, **updates)
    await send_card(
        interaction.response.send_message, "Policy acceptance enabled",
        f"New members will be DM'd the acceptance card on join.\n\n"
        f"- [Privacy Policy]({config['policy_privacy_url']})\n"
        f"- [Terms of Service]({config['policy_terms_url']})\n\n"
        f"Re-send it to existing members with `/policy resend`.",
        accent=GREEN, ephemeral=True,
    )


@policy_group.command(name="disable", description="Stop requiring policy acceptance.")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
@bounded_command
async def policy_disable(interaction: discord.Interaction):
    await mod_store.update_guild_config(interaction.guild_id, policy_enabled=False)
    await send_card(
        interaction.response.send_message, "Policy acceptance disabled",
        "New members will no longer receive the acceptance card. Existing acceptances are kept.",
        ephemeral=True,
    )


@policy_group.command(name="status", description="Show policy acceptance settings and counts.")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
@bounded_command
async def policy_status(interaction: discord.Interaction):
    config = await mod_store.get_guild_config(interaction.guild_id)
    accepted = len(config.get("policy_acceptances", {}))
    await send_card(
        interaction.response.send_message, "Policy acceptance",
        f"**Status:** {'Enabled' if config['policy_enabled'] else 'Disabled'}\n"
        f"**Accepted:** {accepted:,} member(s)\n\n"
        f"- [Privacy Policy]({config['policy_privacy_url']})\n"
        f"- [Terms of Service]({config['policy_terms_url']})",
        accent=GREEN if config["policy_enabled"] else None,
        ephemeral=True,
    )


@policy_group.command(name="check", description="Review one member's policy acceptance.")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
@bounded_command
async def policy_check(interaction: discord.Interaction, member: discord.Member):
    config = await mod_store.get_guild_config(interaction.guild_id)
    record = config.get("policy_acceptances", {}).get(str(member.id))
    if record:
        await send_card(
            interaction.response.send_message, "Policy accepted",
            f"{member.mention} accepted the policies on "
            f"<t:{int(datetime.fromisoformat(record['accepted_at']).timestamp())}:f> "
            f"(via {record.get('via', 'unknown')}).",
            accent=GREEN, ephemeral=True,
        )
    else:
        await send_card(
            interaction.response.send_message, "Not yet accepted",
            f"{member.mention} has not accepted the policies. Re-send the card with `/policy resend`.",
            error=True, ephemeral=True,
        )


@policy_group.command(name="resend", description="Re-send the acceptance card to one member.")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
@bounded_command
async def policy_resend(interaction: discord.Interaction, member: discord.Member):
    config = await mod_store.get_guild_config(interaction.guild_id)
    try:
        await member.send(view=_build_policy_card(config, interaction.guild_id))
    except discord.HTTPException:
        await send_card(
            interaction.response.send_message, "Delivery failed",
            f"I couldn't DM {member.mention} — their DMs may be closed. "
            "Ask them to open DMs, then try again.",
            error=True, ephemeral=True,
        )
        return
    await send_card(
        interaction.response.send_message, "Card re-sent",
        f"Acceptance card sent to {member.mention}.",
        ephemeral=True,
    )


def _wants_factory_card(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()
    if not normalized:
        return False
    if full_factory_request(text) and re.search(r"\b(make|build|produce|factory|production|raw)\b", text, re.I):
        return True
    explicit = ("factory", "production line", "production setup", "production plan")
    actions = ("build", "make", "setup", "set up", "produce", "factory")
    if any(term in normalized for term in explicit) and any(term in normalized for term in actions):
        return True
    return bool(re.search(r"\bhow\s+(?:do|can)\s+i\s+(?:make|build)\b|\bhow\s+to\s+(?:make|build)\b|\brecipe\s+for\b", normalized))


def _wants_overbroad_request(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()
    return bool(re.search(r"\b(exhaustive|every|all)\b.*\b(production|chain|item|recipe|wiki)\b", normalized))


def _wants_wiki_count(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()
    return bool(re.search(r"\bhow many\b.*\b(items?|notes?)\b", normalized) and ("capital rift" in normalized or "wiki" in normalized))


def _factory_subject(text: str) -> str:
    subject = re.sub(r"[^a-zA-Z0-9 -]", " ", text or "")
    subject = re.sub(r"\bfacotry\b", "factory", subject, flags=re.IGNORECASE)
    subject = re.sub(r"\b(how|do|i|make|build|create|a|an|the|factory|production|line|setup|plan|for|to|of|in|please|you|capable|produce|producing|per|minute|hour|output|outputs|items?|units?)\b", " ", subject, flags=re.IGNORECASE)
    subject = re.sub(r"\bexcavators\b", "excavator", subject, flags=re.IGNORECASE)
    subject = re.sub(r"\b\d+(?:\.\d+)?\b", " ", subject)
    return re.sub(r"\s+", " ", subject).strip() or "factory"


def _overbroad_result():
    result = AgentResult()
    result.status = "timeout"
    result.text = "That request is too broad to complete reliably in one turn. Try one item or one production chain at a time."
    return result


async def _deterministic_wiki_count_result():
    result = AgentResult()
    payload = json.loads(await capital_rift_wiki("status"))
    data = payload.get("data", {})
    if data.get("error"):
        result.status = "error"
        result.text = f"The Capital Rift wiki is unavailable: {data['error']}"
    else:
        result.status = "completed"
        result.text = f"The local Capital Rift wiki currently contains {int(data.get('totalNotes', 0)):,} notes."
    return result


async def _deterministic_factory_result(request: str, *, amount: float | None = None):
    """Wiki-only factory lookup: no model output between the note and the card."""
    result = AgentResult()
    if amount is not None or full_factory_request(request):
        try:
            from fractions import Fraction
            parsed = FactoryRequest(request.strip(), Fraction(str(amount))) if amount is not None else parse_factory_request(request)
            result.factory_plan = await asyncio.wait_for(
                plan_factory(parsed),
                timeout=timeout_seconds("AGENT_TURN_TIMEOUT_SECONDS", 120),
            )
        except asyncio.TimeoutError:
            result.status = "timeout"
            result.text = "The wiki factory calculation timed out. Try a smaller production chain."
        except (FactoryError, VaultError, OSError) as exc:
            result.status = "error"
            result.text = f"I couldn't calculate the full factory: {exc}"
        return result
    subject = _factory_subject(request)
    note, error = await _capital_rift_note(subject, "recipe")
    if error:
        result.status = "error"
        result.text = error
        return result
    result.status = "completed"
    result.text = ""
    target = None
    match = re.search(r"(?:capable of|at|produce|producing)\s+([0-9]+(?:\.[0-9]+)?)\s+[^?!.]*?\bper\s+minute", request, re.IGNORECASE)
    if match:
        target = float(match.group(1))
    context = {"exact_note": note}
    if target is not None:
        context["target_rate"] = target
    result.wiki_context = json.dumps(context)
    return result


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

    await _respond_to_message(message, content)


@bounded_message
async def _respond_to_message(message, content):
    is_factory = _wants_factory_card(content)
    try:
        async with typing_scope(message.channel):
            history = await chat_history.get_history(message.channel.id, limit=HISTORY_LIMIT)
            if _wants_overbroad_request(content):
                result = _overbroad_result()
            elif _wants_wiki_count(content):
                result = await _deterministic_wiki_count_result()
            elif is_factory:
                result = await _deterministic_factory_result(content)
            else:
                result = await run_agent(history, content)
    except Exception:
        trace_event("handler_error", status="error")
        await send_card(
            message.channel.send, "Request incomplete",
            "I couldn't complete this request. Please try again in a moment.", error=True,
        )
        return

    # Stop typing before Discord delivery or persistence; failed turns should
    # not become factual conversation context for subsequent requests.
    await _send_agent_result(
        message.channel, result, card=is_factory, factory=is_factory,
        factory_name=_factory_subject(content),
    )
    if result.status == "completed" and result.text:
        await chat_history.append_message(message.channel.id, "user", content, max_history=HISTORY_LIMIT)
        await chat_history.append_message(message.channel.id, "assistant", result.text, max_history=HISTORY_LIMIT)


@tree.command(name="ask", description="Ask the AI agent a one-off question (with live web search).")
@app_commands.describe(question="What do you want to ask?")
@bounded_command
async def ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)
    is_factory = _wants_factory_card(question)
    try:
        if _wants_overbroad_request(question):
            result = _overbroad_result()
        elif _wants_wiki_count(question):
            result = await _deterministic_wiki_count_result()
        elif is_factory:
            result = await _deterministic_factory_result(question)
        else:
            result = await run_agent([], question)
    except Exception as e:
        trace_event("handler_error", status="error")
        await send_card(interaction.followup.send, "Request failed", "I could not complete this request. Please try again.", error=True)
        return
    await _send_agent_result(
        interaction, result, followup=True, card=is_factory, factory=is_factory,
        factory_name=_factory_subject(question),
    )


# ---------------------------------------------------------------------------
# Babylon Stock Market commands (public, read-only)
# ---------------------------------------------------------------------------

async def _market_companies(interaction: discord.Interaction):
    try:
        return await market_client.get_companies()
    except BabylonAPIError as exc:
        trace_event("market_error", status="error", error_type=type(exc).__name__)
        await send_card(
            interaction.followup.send, "Market unavailable",
            f"Market data is unavailable: {exc}", error=True, ephemeral=True,
        )
        return None


def _company_url(company_id: str) -> str:
    return f"{BABYLON_SITE_BASE}/companies/{company_id}"


@tree.command(name="market", description="Show a live overview of the Babylon Stock Market.")
@bounded_command
async def market(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    companies = await _market_companies(interaction)
    if companies is None:
        return
    if not companies:
        await send_card(
            interaction.followup.send, "Babylon Stock Market",
            "The Babylon market currently has no listed companies.",
            footer=f"Public market data · cached for up to {BABYLON_CACHE_SECONDS:g} seconds",
        )
        return

    leaders = rank_companies(companies, "value")[:5]
    total_cap = sum(company.total_value for company in companies)
    verified = sum(company.verified for company in companies)
    lines = [
        f"**{index}. [{company.name}]({_company_url(company.id)})** — "
        f"{format_currency(company.total_value)} · {format_percent(company.trend_pct)}"
        for index, company in enumerate(leaders, start=1)
    ]
    body = (
        "\n".join(lines)
        + f"\n\n**Listed companies:** {len(companies):,}"
        + f"\n**Combined value:** {format_currency(total_cap)}"
        + f"\n**Verified:** {verified:,}/{len(companies):,}"
    )
    await send_card(
        interaction.followup.send,
        f"[Babylon Stock Market]({BABYLON_SITE_BASE})",
        body,
        footer=f"Public market data · cached for up to {BABYLON_CACHE_SECONDS:g} seconds",
    )


@tree.command(name="stock", description="Look up a company on the Babylon Stock Market.")
@app_commands.describe(company="Company name")
@bounded_command
async def stock(interaction: discord.Interaction, company: str):
    await interaction.response.defer(thinking=True)
    companies = await _market_companies(interaction)
    if companies is None:
        return
    match = find_company(companies, company)
    if match is None:
        await send_card(
            interaction.followup.send, "Company not found",
            f"I couldn't find a listed company matching `{company[:100]}`.",
            error=True, ephemeral=True,
        )
        return

    body = (
        ("Verified Capital Rift company" if match.verified else "Unverified company")
        + f"\n\n**Share price:** {format_currency(match.share_price)}"
        + f"\n**Trend:** {format_percent(match.trend_pct)}"
        + f"\n**Total value:** {format_currency(match.total_value)}"
        + f"\n**Net worth:** {format_currency(match.net_worth)}"
        + f"\n**Profit/min:** {format_currency(match.profit_per_min)}"
        + f"\n**Funded capital:** {format_currency(match.funded_capital)}"
    )
    if match.last_synced_at:
        body += f"\n**Last synchronized:** <t:{int(match.last_synced_at.timestamp())}:R>"
    await send_card(
        interaction.followup.send,
        f"[{match.name}]({_company_url(match.id)})",
        body,
        accent=GREEN if match.trend_pct >= 0 else None,
        footer=f"Babylon market · cached for up to {BABYLON_CACHE_SECONDS:g} seconds",
    )


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
@bounded_command
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
    await send_card(
        interaction.followup.send,
        f"Market leaders · {metric.name}",
        "\n".join(lines) or "No companies are currently listed.",
        footer=f"Public market data · cached for up to {BABYLON_CACHE_SECONDS:g} seconds",
    )


@tree.command(name="movers", description="Show the Babylon market's biggest gains and losses.")
@app_commands.describe(limit="Number of gainers and losers to show")
@bounded_command
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

    body = f"**Gainers**\n{mover_lines(gainers)}\n\n**Losers**\n{mover_lines(losers)}"
    await send_card(
        interaction.followup.send, "Market movers", body,
        footer=f"Public market data · cached for up to {BABYLON_CACHE_SECONDS:g} seconds",
    )


@tree.command(name="market-status", description="Check verification and synchronization health.")
@bounded_command
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
    body = (
        "Market API online. All listed company snapshots are current."
        if healthy
        else "Market API online. Some company snapshots have not recently refreshed."
    )
    body += (
        f"\n\n**Verified:** {status.verified:,}/{status.total:,}"
        f"\n**Fresh (≤{BABYLON_FRESH_AFTER_MINUTES}m):** {status.fresh:,}"
        f"\n**Delayed (≤{BABYLON_OUTDATED_AFTER_HOURS}h):** {status.delayed:,}"
        f"\n**Outdated (>{BABYLON_OUTDATED_AFTER_HOURS}h):** {status.outdated:,}"
        f"\n**Missing sync time:** {status.missing_sync_time:,}"
    )
    if status.newest_sync:
        body += f"\n**Newest synchronization:** <t:{int(status.newest_sync.timestamp())}:R>"
    if status.oldest_sync:
        body += f"\n**Oldest synchronization:** <t:{int(status.oldest_sync.timestamp())}:R>"
    await send_card(
        interaction.followup.send, "Babylon market status", body,
        accent=GREEN if healthy else ORANGE,
        footer="Verification and synchronization health",
    )


@tree.command(name="image", description="Generate an image from a text prompt.")
@app_commands.describe(prompt="Describe the image you want.")
@bounded_command
async def image(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer(thinking=True)
    try:
        result = await run_agent([], f"Generate an image: {prompt}")
    except Exception as e:
        trace_event("handler_error", status="error")
        await send_card(interaction.followup.send, "Image failed", "I could not complete this request. Please try again.", error=True)
        return
    await _send_agent_result(interaction, result, followup=True, card=True)


@tree.command(name="gif", description="Generate a short animated GIF from a text prompt.")
@app_commands.describe(prompt="Describe the animation/scene you want.")
@bounded_command
async def gif(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer(thinking=True)
    try:
        result = await run_agent([], f"Generate an animated GIF: {prompt}")
    except Exception as e:
        trace_event("handler_error", status="error")
        await send_card(interaction.followup.send, "GIF failed", "I could not complete this request. Please try again.", error=True)
        return
    await _send_agent_result(interaction, result, followup=True, card=True)


@tree.command(name="clearhistory", description="Forget the AI's conversation memory for this channel/DM.")
async def clearhistory(interaction: discord.Interaction):
    await chat_history.clear_history(interaction.channel_id)
    await send_card(
        interaction.response.send_message, "History cleared",
        "Conversation history for this channel has been cleared.", ephemeral=True,
    )


@tree.command(name="build", description="Generate code or a website and get it as a downloadable zip.")
@app_commands.describe(description="Describe what you want built.")
@bounded_command
async def build(interaction: discord.Interaction, description: str):
    await interaction.response.defer(thinking=True)
    try:
        result = await run_agent(
            [],
            f"Build the following and package it with package_files: {description}",
        )
    except Exception as e:
        trace_event("handler_error", status="error")
        await send_card(interaction.followup.send, "Build failed", "I could not complete this request. Please try again.", error=True)
        return
    await _send_agent_result(interaction, result, followup=True, card=True)


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


def _configuration_body(guild: discord.Guild, config: dict) -> str:
    admin_role = guild.get_role(config.get("admin_role_id") or 0)
    market_channel = guild.get_channel(config.get("market_channel_id") or 0)
    mod_log_channel = guild.get_channel(config.get("mod_log_channel_id") or 0)

    return (
        ("Initial setup is complete."
         if config.get("setup_complete")
         else "Initial setup has not been completed.")
        + f"\n\n**Bot administrators:** "
        + (admin_role.mention if admin_role else "Members with Manage Server")
        + f"\n**Market channel:** "
        + (market_channel.mention if market_channel else "Not configured")
        + f"\n**Market alerts:** "
        + ("Enabled" if config.get("market_alerts_enabled") else "Disabled")
        + f"\n**Moderation log:** "
        + (mod_log_channel.mention if mod_log_channel else "Not configured")
    )


async def _send_configuration_card(interaction: discord.Interaction, config: dict, *, prefix: str | None = None):
    body = (prefix + "\n\n" if prefix else "") + _configuration_body(interaction.guild, config)
    await send_card(interaction.response.send_message, "Babylon bot configuration", body, ephemeral=True)


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
    await _send_configuration_card(interaction, config)


@config_group.command(name="view", description="Show this server's current bot settings.")
@app_commands.guild_only()
@bot_admin_only()
async def config_view(interaction: discord.Interaction):
    config = await mod_store.get_guild_config(interaction.guild_id)
    await _send_configuration_card(interaction, config)


@config_group.command(name="admin-role", description="Choose the role that can manage bot settings.")
@app_commands.guild_only()
@bot_admin_only()
async def config_admin_role(interaction: discord.Interaction, role: discord.Role):
    config = await mod_store.update_guild_config(
        interaction.guild_id, admin_role_id=role.id, setup_complete=True
    )
    await _send_configuration_card(interaction, config)


@config_group.command(name="market-channel", description="Choose the channel for market updates.")
@app_commands.guild_only()
@bot_admin_only()
async def config_market_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
    config = await mod_store.update_guild_config(
        interaction.guild_id, market_channel_id=channel.id, setup_complete=True
    )
    await _send_configuration_card(interaction, config)


@config_group.command(name="alerts", description="Enable or disable automated market alerts.")
@app_commands.guild_only()
@bot_admin_only()
async def config_alerts(interaction: discord.Interaction, enabled: bool):
    config = await mod_store.update_guild_config(
        interaction.guild_id, market_alerts_enabled=enabled
    )
    await _send_configuration_card(interaction, config)


@config_group.command(name="reset", description="Reset bot settings but keep moderation warnings.")
@app_commands.describe(confirm="Must be true to confirm the reset")
@app_commands.guild_only()
@bot_admin_only()
async def config_reset(interaction: discord.Interaction, confirm: bool):
    if not confirm:
        await send_card(
            interaction.response.send_message, "Reset cancelled",
            "Nothing was reset. Run the command with confirm set to True to continue.",
            ephemeral=True,
        )
        return

    config = await mod_store.reset_guild_config(
        interaction.guild_id, preserve_warnings=True
    )
    await _send_configuration_card(
        interaction, config,
        prefix="Server bot settings were reset. Moderation warning history was preserved.",
    )


@tree.command(name="wiki-status", description="Check the local Capital Rift wiki index.")
@app_commands.guild_only()
@bot_admin_only()
@bounded_command
async def wiki_status(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    payload = json.loads(await capital_rift_wiki("status"))
    data = payload.get("data", {})
    error = data.get("error")
    if error:
        await send_card(
            interaction.followup.send, "Wiki unavailable",
            f"Capital Rift wiki is not ready: {error}", error=True, ephemeral=True,
        )
        return

    await send_card(
        interaction.followup.send, "Capital Rift wiki",
        f"Indexed notes: **{data.get('totalNotes', 0):,}**\nVault access: **read-only**",
        footer="Local wiki index", ephemeral=True,
    )


@tree.command(name="status", description="Check bot health, integrations, and setup completeness.")
@app_commands.guild_only()
@bot_admin_only()
@bounded_command
async def status(interaction: discord.Interaction):
    """One actionable health card: gateway, wiki, market, keys, and guild setup."""
    await interaction.response.defer(ephemeral=True, thinking=True)
    lines: list[str] = []
    warnings = 0

    def report(ok: bool, text: str, hint: str | None = None) -> None:
        nonlocal warnings
        if ok:
            lines.append(f"✅ {text}")
        else:
            warnings += 1
            lines.append(f"⚠️ {text}" + (f" — {hint}" if hint else ""))

    latency_ms = round(client.latency * 1000) if client.latency else None
    report(
        latency_ms is not None and latency_ms < 1000,
        f"Discord gateway: {latency_ms}ms heartbeat" if latency_ms is not None else "Discord gateway: no heartbeat yet",
    )

    try:
        payload = json.loads(await capital_rift_wiki("status"))
        data = payload.get("data", {})
        if data.get("error"):
            report(False, f"Capital Rift wiki: {data['error']}", "check CAPITAL_RIFT_VAULT_PATH in .env")
        else:
            report(True, f"Capital Rift wiki: {int(data.get('totalNotes', 0)):,} notes indexed")
    except Exception as exc:
        report(False, f"Capital Rift wiki: {type(exc).__name__}", "check CAPITAL_RIFT_VAULT_PATH in .env")

    try:
        companies = await market_client.get_companies()
        report(True, f"Babylon market API: {len(companies):,} companies listed")
    except BabylonAPIError as exc:
        report(False, f"Babylon market API: {exc}", "market commands will degrade")

    report(
        bool(os.environ.get("NVIDIA_API_KEY", "").strip()),
        "NVIDIA API key configured",
        "AI chat and moderation need NVIDIA_API_KEY in .env",
    )
    report(
        bool(os.environ.get("TAVILY_API_KEY", "").strip()),
        "Tavily web search configured",
        "optional; live web search needs TAVILY_API_KEY",
    )

    config = await mod_store.get_guild_config(interaction.guild_id)
    report(
        bool(config.get("setup_complete")),
        "Server setup completed",
        "run /setup to complete initial configuration",
    )
    report(
        bool(config.get("admin_role_id")),
        "Bot admin role selected",
        "set one with /config admin-role",
    )
    report(
        bool(config.get("market_channel_id")),
        "Market channel selected",
        "set one with /config market-channel",
    )
    report(
        bool(config.get("mod_log_channel_id")),
        "Moderation log channel selected",
        "set one with /modlog",
    )

    await send_card(
        interaction.followup.send, "Babylon Helper status",
        "\n".join(lines),
        accent=GREEN if warnings == 0 else ORANGE,
        footer=f"{warnings} warning(s)" if warnings else "All systems nominal",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Capital Rift direct wiki commands (no AI tool-calling required)
# ---------------------------------------------------------------------------

async def _send_wiki_card(interaction, title, note):
    card = await linked_wiki_card(note)
    await send_card(interaction.followup.send, title, **card)


async def _capital_rift_note(query: str, kind: str) -> tuple[dict | None, str | None]:
    """Search then read the strongest local-wiki match for a typed lookup."""
    payload = json.loads(await capital_rift_wiki("search", query=f"{query} {kind}", limit=5))
    data = payload.get("data", {})
    if data.get("error"):
        return None, data["error"]
    results = data.get("results") or []
    if not results:
        return None, f"No {kind} matching '{query[:100]}' was found in the Capital Rift wiki."

    def normalize(value: str) -> str:
        return re.sub(r"[_-]+", " ", re.sub(r"\s+", " ", value.casefold().strip()))
    normalized_query = normalize(query)
    result = next(
        (
            item for item in results
            if normalize(item.get("title", "")) == normalized_query
            or normalize(item.get("path", "").rsplit("/", 1)[-1].removesuffix(".md")) == normalized_query
        ),
        None,
    )
    if result is None:
        return None, f"No exact {kind} named **{query[:100]}** was found in the Capital Rift wiki."
    payload = json.loads(await capital_rift_wiki("read", note_path=result["path"]))
    data = payload.get("data", {})
    if data.get("error"):
        return None, data["error"]
    return data, None


@tree.command(name="item", description="Look up a Capital Rift item in the local wiki.")
@app_commands.describe(name="Item name, for example Iron Plate")
@bounded_command
async def item_lookup(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True)
    note, error = await _capital_rift_note(name, "item")
    if error:
        await send_card(interaction.followup.send, "Wiki lookup unavailable", error, error=True, ephemeral=True)
        return
    await _send_wiki_card(interaction, f"Item · {note.get('title', name)}", note)


@tree.command(name="recipe", description="Look up a Capital Rift recipe in the local wiki.")
@app_commands.describe(name="Recipe or output item name, for example Iron Plate")
@bounded_command
async def recipe_lookup(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True)
    note, error = await _capital_rift_note(name, "recipe")
    if error:
        await send_card(interaction.followup.send, "Wiki lookup unavailable", error, error=True, ephemeral=True)
        return
    await _send_wiki_card(interaction, f"Recipe · {note.get('title', name)}", note)


@tree.command(name="machine", description="Look up a Capital Rift production machine in the local wiki.")
@app_commands.describe(name="Machine name, for example Furnace")
@bounded_command
async def machine_lookup(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True)
    note, error = await _capital_rift_note(name, "machine")
    if error:
        await send_card(interaction.followup.send, "Wiki lookup unavailable", error, error=True, ephemeral=True)
        return
    await _send_wiki_card(interaction, f"Machine · {note.get('title', name)}", note)


@tree.command(name="factory", description="Create a wiki-grounded factory or production setup card.")
@app_commands.describe(
    item="Item to produce, for example Computer or Bucket-Wheel Excavator",
    amount="Output per minute (e.g. 1 or 0.1). Leave blank for a basic factory lookup.",
)
@bounded_command
async def factory(
    interaction: discord.Interaction,
    item: str,
    amount: app_commands.Range[float, 0.000001, 1000000.0] | None = None,
):
    await interaction.response.defer(thinking=True)
    result = await _deterministic_factory_result(item, amount=amount)
    await _send_agent_result(
        interaction, result, followup=True, card=True, factory=True,
        factory_name=item,
    )


@tree.command(name="production", description="Calculate machines required for a Capital Rift output target.")
@app_commands.describe(
    item="Exact output item name, for example Iron Plate (autocompletes from the wiki)",
    target_per_minute="Desired output per minute",
)
@bounded_command
async def production(interaction: discord.Interaction, item: str, target_per_minute: app_commands.Range[float, 0.001, 1000000.0]):
    await interaction.response.defer(thinking=True)
    note, error = await _capital_rift_note(item, "recipe")
    if error:
        await send_card(
            interaction.followup.send, "Recipe unavailable",
            f"{error}\n\nUse the exact item name — the `item` field autocompletes indexed wiki names.",
            error=True, ephemeral=True,
        )
        return

    recipe = parse_recipe(note)
    if recipe.rate is None:
        details = "\n".join(f"- {issue}" for issue in recipe.issues) or \
            "- The wiki note does not publish a per-minute output rate."
        await send_card(
            interaction.followup.send, "Rate unavailable",
            f"I found the recipe, but its wiki data is incomplete, so I will not guess the machine count:\n"
            f"{details}\n\nSource: {note.get('path', 'unknown')}",
            error=True, ephemeral=True,
        )
        return

    rate = float(recipe.rate)
    machines = max(1, math.ceil(float(target_per_minute) / rate))
    actual_output = machines * rate
    machine = recipe.machine or "the recipe machine"
    body = (
        f"Target: **{float(target_per_minute):g}/min**\n"
        f"Recipe rate: **{rate:g}/min per machine**\n"
        f"Machines needed: **{machines:,} {machine}**\n"
        f"Output at full capacity: **{actual_output:g}/min**"
    )
    await send_card(
        interaction.followup.send, f"Production plan · {recipe.name}", body,
        accent=GREEN, footer=f"Capital Rift wiki · Source: {note.get('path', 'unknown')}",
    )


@production.autocomplete("item")
async def production_item_autocomplete(
    _interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not current.strip():
        return []
    try:
        payload = json.loads(await capital_rift_wiki("search", query=current, limit=10))
    except Exception:
        return []
    titles = [item.get("title", "").strip() for item in payload.get("data", {}).get("results") or []]
    return [
        app_commands.Choice(name=title[:100], value=title[:100])
        for title in titles
        if title
    ][:10]


@tree.error
@bounded_command
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        message = str(error) or "You don't have permission to use this command."
        send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await send_card(send, "Command unavailable", message, error=True, ephemeral=True)
        return
    trace_event("handler_error", status="error")
    send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    await send_card(send, "Command failed", "I could not complete this command. Please try again.", error=True, ephemeral=True)


@automod_group.command(name="toggle", description="Turn automod on or off for this server.")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_toggle(interaction: discord.Interaction, enabled: bool):
    await mod_store.update_guild_config(interaction.guild_id, automod_enabled=enabled)
    await send_card(
        interaction.response.send_message, "Automod",
        f"Automod is now **{'ON' if enabled else 'OFF'}**.", ephemeral=True,
    )


@automod_group.command(name="addword", description="Add a word/phrase to the banned list.")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_addword(interaction: discord.Interaction, word: str):
    config = await mod_store.get_guild_config(interaction.guild_id)
    words = config["banned_words"]
    if word.lower() not in [w.lower() for w in words]:
        words.append(word)
        await mod_store.update_guild_config(interaction.guild_id, banned_words=words)
    await send_card(
        interaction.response.send_message, "Banned words",
        f"Added `{word}` to the banned word list.", ephemeral=True,
    )


@automod_group.command(name="removeword", description="Remove a word/phrase from the banned list.")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_removeword(interaction: discord.Interaction, word: str):
    config = await mod_store.get_guild_config(interaction.guild_id)
    words = [w for w in config["banned_words"] if w.lower() != word.lower()]
    await mod_store.update_guild_config(interaction.guild_id, banned_words=words)
    await send_card(
        interaction.response.send_message, "Banned words",
        f"Removed `{word}` from the banned word list.", ephemeral=True,
    )


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
    await send_card(interaction.response.send_message, "Automod settings", text, ephemeral=True)


@automod_group.command(
    name="ai-toggle",
    description="Turn AI-powered moderation on/off (catches harassment/hate/threats without exact banned words).",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_ai_toggle(interaction: discord.Interaction, enabled: bool):
    await mod_store.update_guild_config(interaction.guild_id, ai_automod_enabled=enabled)
    body = f"AI-powered moderation is now **{'ON' if enabled else 'OFF'}**."
    if enabled:
        body += (
            "\n\nIt runs on every message that passes keyword automod and is at least the configured "
            "minimum length — use `/automod ai-settings` to tune that."
        )
    await send_card(interaction.response.send_message, "AI moderation", body, ephemeral=True)


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
    await send_card(interaction.response.send_message, "AI moderation settings", text, ephemeral=True)


@raid_group.command(name="mode", description="Manually turn raid lockdown mode on or off.")
@app_commands.checks.has_permissions(manage_guild=True)
async def raid_mode(interaction: discord.Interaction, enabled: bool):
    await mod_store.update_guild_config(interaction.guild_id, raid_mode_active=enabled)
    await send_card(
        interaction.response.send_message, "Raid mode",
        f"Raid mode is now **{'ON' if enabled else 'OFF'}**.", ephemeral=True,
    )


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
    await send_card(interaction.response.send_message, "Raid protection settings", text, ephemeral=True)


# ---------------------------------------------------------------------------
# Configurable reaction roles
# ---------------------------------------------------------------------------

reactionroles_group = app_commands.Group(
    name="reactionroles",
    description="Configure self-service roles granted by reacting to a message.",
)

_CUSTOM_EMOJI_ID = re.compile(r"<:?[^:<>]+:(\d+)>")


def _emoji_matches(stored: str, reacted: str) -> bool:
    """Match stored emoji text against a raw-reaction emoji string."""
    if not stored or not reacted:
        return False
    stored_id = _CUSTOM_EMOJI_ID.search(stored)
    reacted_id = _CUSTOM_EMOJI_ID.search(reacted)
    if stored_id and reacted_id:
        return stored_id.group(1) == reacted_id.group(1)
    return stored == reacted


def _find_reaction_mapping(config: dict, channel_id: int, message_id: int, emoji: str) -> dict | None:
    channel_key = str(channel_id)
    message_key = str(message_id)
    for entry in config.get("reaction_roles", []):
        if (
            entry.get("channel_id") == channel_key
            and entry.get("message_id") == message_key
            and _emoji_matches(str(entry.get("emoji", "")), emoji)
        ):
            return entry
    return None


def _reaction_role_issues(role: discord.Role, me: discord.Member) -> list[str]:
    """Why this role cannot be used as a reaction role, empty when safe."""
    issues = []
    if role.is_default():
        issues.append("@everyone cannot be a reaction role.")
    if role.managed:
        issues.append(f"{role.name} is managed by an integration and cannot be assigned.")
    if me is not None and getattr(role, "position", 0) >= getattr(me.top_role, "position", 0):
        issues.append(
            f"{role.name} is not below my highest role ({me.top_role.name}); move my role higher first."
        )
    if me is not None and not me.guild_permissions.manage_roles:
        issues.append("I need the Manage Roles permission.")
    return issues


def _parse_message_ref(ref: str) -> tuple[int, int] | tuple[None, None]:
    """Accept a bare message ID or a discord.com message link."""
    ref = (ref or "").strip()
    match = re.search(r"channels/\d+/(\d+)/(\d+)", ref)
    if match:
        return int(match.group(1)), int(match.group(2))
    if ref.isdigit():
        return None, int(ref)
    return None, None


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    await _handle_raw_reaction(payload, add=True)


@client.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    await _handle_raw_reaction(payload, add=False)


async def _handle_raw_reaction(payload: discord.RawReactionActionEvent, *, add: bool) -> None:
    if payload.guild_id is None or payload.user_id == getattr(client.user, "id", None):
        return
    try:
        config = await mod_store.get_guild_config(payload.guild_id)
        entry = _find_reaction_mapping(
            config, payload.channel_id, payload.message_id, str(payload.emoji)
        )
        if entry is None:
            return
        guild = client.get_guild(payload.guild_id)
        member = payload.member if add else (guild.get_member(payload.user_id) if guild else None)
        if guild is None or member is None or member.bot:
            return
        role = guild.get_role(int(entry["role_id"]))
        if role is None or _reaction_role_issues(role, guild.me):
            return
        if add:
            await member.add_roles(role, reason="Reaction role")
        else:
            await member.remove_roles(role, reason="Reaction role removed")
    except discord.HTTPException:
        log.warning("Reaction role update failed for guild %s", payload.guild_id)
    except Exception:
        log.exception("Reaction role handler error")


@reactionroles_group.command(name="add", description="Map an emoji on a message to a self-service role.")
@app_commands.describe(
    message="Message ID or discord.com message link",
    emoji="Emoji to watch for (custom emoji pasted as its :name:id form works)",
    role="Role members receive when reacting",
    channel="Channel containing the message (required for bare IDs)",
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
@bounded_command
async def reactionroles_add(
    interaction: discord.Interaction,
    message: str,
    emoji: str,
    role: discord.Role,
    channel: discord.TextChannel | None = None,
):
    link_channel_id, link_message_id = _parse_message_ref(message)
    channel_id = link_channel_id or (channel.id if channel is not None else None)
    message_id = link_message_id
    if channel_id is None or message_id is None:
        await send_card(
            interaction.response.send_message, "Message needed",
            "Pass a discord.com message link, or a bare message ID together with the `channel` option.",
            error=True, ephemeral=True,
        )
        return

    issues = _reaction_role_issues(role, interaction.guild.me)
    if issues:
        await send_card(
            interaction.response.send_message, "Role not usable",
            "\n".join(f"- {issue}" for issue in issues), error=True, ephemeral=True,
        )
        return

    target_channel = interaction.guild.get_channel(channel_id)
    if target_channel is None:
        await send_card(
            interaction.response.send_message, "Channel not found",
            f"I can't see channel {channel_id}. Check the link or pass `channel`.",
            error=True, ephemeral=True,
        )
        return

    try:
        target_message = await target_channel.fetch_message(message_id)
        await target_message.add_reaction(emoji)
    except discord.HTTPException as exc:
        await send_card(
            interaction.response.send_message, "Message not reachable",
            f"I couldn't read that message or react with `{emoji}`: {exc}",
            error=True, ephemeral=True,
        )
        return

    config = await mod_store.get_guild_config(interaction.guild_id)
    mappings = [
        entry for entry in config["reaction_roles"]
        if not (str(entry.get("channel_id")) == str(channel_id)
                and str(entry.get("message_id")) == str(message_id)
                and _emoji_matches(str(entry.get("emoji", "")), emoji))
    ]
    mappings.append({
        "channel_id": str(channel_id),
        "message_id": str(message_id),
        "emoji": emoji,
        "role_id": str(role.id),
    })
    await mod_store.update_guild_config(interaction.guild_id, reaction_roles=mappings)
    await send_card(
        interaction.response.send_message, "Reaction role added",
        f"Reacting with {emoji} on [the message]({target_message.jump_url}) now grants {role.mention}.\n"
        f"Removing the reaction revokes it.",
        ephemeral=True,
    )


@reactionroles_group.command(name="remove", description="Remove one reaction-role mapping.")
@app_commands.describe(message="Message ID or link used when the mapping was created", emoji="Emoji of the mapping")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
@bounded_command
async def reactionroles_remove(interaction: discord.Interaction, message: str, emoji: str):
    channel_id, message_id = _parse_message_ref(message)
    config = await mod_store.get_guild_config(interaction.guild_id)
    mappings = list(config["reaction_roles"])
    kept = [
        entry for entry in mappings
        if not (
            (channel_id is None or str(entry.get("channel_id")) == str(channel_id))
            and (message_id is None or str(entry.get("message_id")) == str(message_id))
            and _emoji_matches(str(entry.get("emoji", "")), emoji)
        )
    ]
    if len(kept) == len(mappings):
        await send_card(
            interaction.response.send_message, "Mapping not found",
            f"No reaction-role mapping matches `{emoji}` on that message.",
            error=True, ephemeral=True,
        )
        return
    await mod_store.update_guild_config(interaction.guild_id, reaction_roles=kept)
    await send_card(
        interaction.response.send_message, "Reaction role removed",
        f"Removed {len(mappings) - len(kept)} mapping(s) for `{emoji}` on that message.",
        ephemeral=True,
    )


@reactionroles_group.command(name="list", description="Show this server's reaction-role mappings.")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
@bounded_command
async def reactionroles_list(interaction: discord.Interaction):
    config = await mod_store.get_guild_config(interaction.guild_id)
    mappings = config["reaction_roles"]
    if not mappings:
        await send_card(
            interaction.response.send_message, "Reaction roles",
            "No reaction-role mappings are configured yet. Create one with `/reactionroles add`.",
            ephemeral=True,
        )
        return
    lines = []
    for index, entry in enumerate(mappings, start=1):
        role = interaction.guild.get_role(int(entry["role_id"]))
        role_text = role.mention if role else f"deleted role `{entry['role_id']}`"
        channel = interaction.guild.get_channel(int(entry["channel_id"]))
        channel_text = channel.mention if channel else f"channel `{entry['channel_id']}`"
        lines.append(
            f"{index}. {entry['emoji']} → {role_text} · {channel_text} · [message](https://discord.com/channels/"
            f"{interaction.guild_id}/{entry['channel_id']}/{entry['message_id']})"
        )
    await send_card(
        interaction.response.send_message, "Reaction roles",
        "\n".join(lines), footer=f"{len(mappings)} mapping(s)", ephemeral=True,
    )


tree.add_command(automod_group)
tree.add_command(raid_group)
tree.add_command(config_group)
tree.add_command(reactionroles_group)
tree.add_command(policy_group)


@tree.command(name="modlog", description="Set the channel moderation events get logged to.")
@app_commands.checks.has_permissions(manage_guild=True)
async def modlog(interaction: discord.Interaction, channel: discord.TextChannel):
    await mod_store.update_guild_config(interaction.guild_id, mod_log_channel_id=channel.id)
    await send_card(
        interaction.response.send_message, "Mod log",
        f"Mod log set to {channel.mention}.", ephemeral=True,
    )


@tree.command(name="warn", description="Warn a user (logged, DM'd, no other action taken).")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    count = await mod_store.add_warning(interaction.guild_id, member.id)
    await _mod_log(interaction.guild, f"⚠️ {interaction.user.mention} warned {member.mention} — {reason} (warning #{count})")
    try:
        await member.send(f"You were warned in **{interaction.guild.name}**: {reason}")
    except discord.Forbidden:
        pass
    await send_card(
        interaction.response.send_message, "Warning issued",
        f"Warned {member.mention} (warning #{count}).", ephemeral=True,
    )


@tree.command(name="timeout", description="Time out a user for a number of minutes.")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout_cmd(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason given"):
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    try:
        await member.timeout(until, reason=reason)
    except discord.Forbidden:
        await send_card(
            interaction.response.send_message, "Timeout failed",
            "I don't have permission to time out that user.", error=True, ephemeral=True,
        )
        return
    await _mod_log(interaction.guild, f"⏱️ {interaction.user.mention} timed out {member.mention} for {minutes}m — {reason}")
    await send_card(
        interaction.response.send_message, "Timeout issued",
        f"Timed out {member.mention} for {minutes} minutes.", ephemeral=True,
    )


@tree.command(name="kick", description="Kick a user from the server.")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
    try:
        await member.kick(reason=reason)
    except discord.Forbidden:
        await send_card(
            interaction.response.send_message, "Kick failed",
            "I don't have permission to kick that user.", error=True, ephemeral=True,
        )
        return
    await _mod_log(interaction.guild, f"👢 {interaction.user.mention} kicked {member.mention} — {reason}")
    await send_card(
        interaction.response.send_message, "Member kicked",
        f"Kicked {member.mention}.", ephemeral=True,
    )


@tree.command(name="ban", description="Ban a user from the server.")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
    try:
        await member.ban(reason=reason, delete_message_seconds=0)
    except discord.Forbidden:
        await send_card(
            interaction.response.send_message, "Ban failed",
            "I don't have permission to ban that user.", error=True, ephemeral=True,
        )
        return
    await _mod_log(interaction.guild, f"🔨 {interaction.user.mention} banned {member.mention} — {reason}")
    await send_card(
        interaction.response.send_message, "Member banned",
        f"Banned {member.mention}.", ephemeral=True,
    )


@tree.command(name="purge", description="Delete a number of recent messages in this channel.")
@app_commands.checks.has_permissions(manage_messages=True)
@bounded_command
async def purge(interaction: discord.Interaction, count: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True, thinking=True)
    deleted = await interaction.channel.purge(limit=count)
    await _mod_log(interaction.guild, f"🧹 {interaction.user.mention} purged {len(deleted)} messages in {interaction.channel.mention}")
    await send_card(
        interaction.followup.send, "Purge complete",
        f"Deleted {len(deleted)} messages.", ephemeral=True,
    )


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
