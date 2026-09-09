import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from moderation import store


def make_member(member_id=500, *, dm_fails=False, guild_id=900, roles=()):
    member = SimpleNamespace(
        id=member_id, bot=False,
        guild=SimpleNamespace(
            id=guild_id, get_role=lambda _role_id: None,
            me=SimpleNamespace(
                top_role=SimpleNamespace(name="BotTop", position=10),
                guild_permissions=SimpleNamespace(manage_roles=True),
            ),
        ),
        roles=list(roles),
        send=AsyncMock(),
        add_roles=AsyncMock(), remove_roles=AsyncMock(),
    )
    if dm_fails:
        import discord

        # Build without __init__: its message formatting needs a real HTTP response.
        forbidden = discord.HTTPException.__new__(discord.HTTPException)

        async def fail(*args, **kwargs):
            raise forbidden

        member.send = fail
    return member


def make_gate_roles(guild_id=900, *, hold_position=1, member_position=2):
    hold = SimpleNamespace(
        id=111, name="Pending", managed=False, is_default=lambda: False,
        position=hold_position,
    )
    member_role = SimpleNamespace(
        id=222, name="Member", managed=False, is_default=lambda: False,
        position=member_position,
    )
    me = SimpleNamespace(
        top_role=SimpleNamespace(name="BotTop", position=10),
        guild_permissions=SimpleNamespace(manage_roles=True),
    )
    roles_by_id = {111: hold, 222: member_role}
    guild = SimpleNamespace(
        id=guild_id, me=me,
        get_role=lambda role_id: roles_by_id.get(role_id),
    )
    return hold, member_role, guild


class PolicyStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.saved = (store.DATA_DIR, store.CONFIG_PATH, store._cache, store._lock)
        store.DATA_DIR = self.temp_dir.name
        store.CONFIG_PATH = os.path.join(self.temp_dir.name, "guild_config.json")
        store._cache = {}
        store._lock = asyncio.Lock()

    async def asyncTearDown(self):
        store.DATA_DIR, store.CONFIG_PATH, store._cache, store._lock = self.saved
        self.temp_dir.cleanup()

    async def test_policy_defaults_and_persistence(self):
        config = await store.get_guild_config(900)
        self.assertFalse(config["policy_enabled"])
        self.assertEqual(config["policy_privacy_url"], "https://holdings.thebabylon.hu/privacy")
        self.assertEqual(config["policy_terms_url"], "https://holdings.thebabylon.hu/terms")
        self.assertEqual(config["policy_acceptances"], {})

        await store.update_guild_config(
            900, policy_enabled=True,
            policy_acceptances={"500": {"accepted_at": "2026-09-09T00:00:00+00:00", "via": "dm-button"}},
        )
        store._cache = {}
        store._load()
        config = await store.get_guild_config(900)
        self.assertTrue(config["policy_enabled"])
        self.assertEqual(config["policy_acceptances"]["500"]["via"], "dm-button")


class PolicyAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        os.environ.setdefault("DISCORD_BOT_TOKEN", "test-only")
        import bot
        self.bot = bot

    async def test_recording_is_idempotent_and_keeps_first_timestamp(self):
        with patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value={
            "policy_acceptances": {},
        })), patch.object(self.bot.mod_store, "update_guild_config", AsyncMock(return_value={})):
            first = await self.bot.record_policy_acceptance(900, 500, via="dm-button")
            second = await self.bot.record_policy_acceptance(900, 500, via="dm-button")
        self.assertEqual(first, second)

    async def test_join_sends_card_only_when_enabled_and_unaccepted(self):
        member = make_member()
        enabled = {"policy_enabled": True, "policy_acceptances": {},
                   "policy_privacy_url": "https://holdings.thebabylon.hu/privacy",
                   "policy_terms_url": "https://holdings.thebabylon.hu/terms",
                   "policy_hold_role_id": None, "policy_member_role_id": None}
        with patch.object(self.bot.raid, "handle_join", AsyncMock()), \
             patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value=enabled)):
            await self.bot.on_member_join(member)
        member.send.assert_awaited_once()
        kwargs = member.send.await_args.kwargs
        self.assertTrue(kwargs["view"].has_components_v2())

        # Already accepted -> no second DM on a repeat join.
        accepted = dict(enabled, policy_acceptances={"500": {"accepted_at": "2026-09-09T00:00:00+00:00", "via": "dm-button"}})
        member.send.reset_mock()
        with patch.object(self.bot.raid, "handle_join", AsyncMock()), \
             patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value=accepted)):
            await self.bot.on_member_join(member)
        member.send.assert_not_awaited()

        # Disabled entirely -> no DM.
        member.send.reset_mock()
        with patch.object(self.bot.raid, "handle_join", AsyncMock()), \
             patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value=dict(enabled, policy_enabled=False))):
            await self.bot.on_member_join(member)
        member.send.assert_not_awaited()

    async def test_join_assigns_hold_role_until_accepted(self):
        hold, member_role, guild = make_gate_roles()
        member = make_member(roles=[])
        member.guild = guild
        config = {"policy_enabled": True, "policy_acceptances": {},
                  "policy_privacy_url": "https://holdings.thebabylon.hu/privacy",
                  "policy_terms_url": "https://holdings.thebabylon.hu/terms",
                  "policy_hold_role_id": 111, "policy_member_role_id": 222}
        with patch.object(self.bot.raid, "handle_join", AsyncMock()), \
             patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value=config)):
            await self.bot.on_member_join(member)
        member.add_roles.assert_awaited_once_with(hold, reason="Policy acceptance pending")
        member.send.assert_awaited_once()

    async def test_acceptance_swaps_hold_for_member_role(self):
        hold, member_role, guild = make_gate_roles()
        member = make_member(roles=[hold])
        member.guild = guild
        config = {"policy_enabled": True,
                  "policy_acceptances": {"500": {"accepted_at": "2026-09-09T00:00:00+00:00", "via": "dm-button"}},
                  "policy_privacy_url": "x", "policy_terms_url": "y",
                  "policy_hold_role_id": 111, "policy_member_role_id": 222}
        await self.bot._apply_policy_gate(member, config, accepted=True)
        member.remove_roles.assert_awaited_once_with(hold, reason="Policy accepted")
        member.add_roles.assert_awaited_once_with(member_role, reason="Policy accepted")
        member.send.assert_not_awaited()

    async def test_repeat_join_of_accepted_member_grants_member_role(self):
        hold, member_role, guild = make_gate_roles()
        member = make_member(roles=[])
        member.guild = guild
        config = {"policy_enabled": True,
                  "policy_acceptances": {"500": {"accepted_at": "2026-09-09T00:00:00+00:00", "via": "dm-button"}},
                  "policy_privacy_url": "x", "policy_terms_url": "y",
                  "policy_hold_role_id": 111, "policy_member_role_id": 222}
        with patch.object(self.bot.raid, "handle_join", AsyncMock()), \
             patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value=config)):
            await self.bot.on_member_join(member)
        member.add_roles.assert_awaited_once_with(member_role, reason="Policy accepted")
        member.send.assert_not_awaited()

    async def test_unsafe_gate_roles_are_skipped_without_blocking(self):
        # Both roles above the bot's top role: nothing is assigned, nothing raises.
        hold, member_role, guild = make_gate_roles(hold_position=50, member_position=60)
        member = make_member(roles=[])
        member.guild = guild
        config = {"policy_enabled": True, "policy_acceptances": {},
                  "policy_privacy_url": "x", "policy_terms_url": "y",
                  "policy_hold_role_id": 111, "policy_member_role_id": 222}
        with patch.object(self.bot, "_mod_log", AsyncMock()) as mod_log:
            await self.bot._apply_policy_gate(member, config, accepted=False)
        member.add_roles.assert_not_awaited()
        self.assertEqual(mod_log.await_count, 2)  # one staff note per unusable role

    async def test_closed_dms_fail_gracefully(self):
        member = make_member(dm_fails=True)
        enabled = {"policy_enabled": True, "policy_acceptances": {},
                   "policy_privacy_url": "https://holdings.thebabylon.hu/privacy",
                   "policy_terms_url": "https://holdings.thebabylon.hu/terms"}
        with patch.object(self.bot.raid, "handle_join", AsyncMock()), \
             patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value=enabled)):
            await self.bot.on_member_join(member)  # must not raise

    async def test_component_click_records_acceptance_for_clicker(self):
        import discord

        interaction = SimpleNamespace(
            type=discord.InteractionType.component,
            data={"custom_id": "policy:accept:900"},
            user=SimpleNamespace(id=500),
            response=SimpleNamespace(send_message=AsyncMock()),
        )
        with patch.object(self.bot, "record_policy_acceptance", AsyncMock(return_value="2026-09-09T00:00:00+00:00")) as record:
            await self.bot.on_interaction(interaction)
        record.assert_awaited_once_with(900, 500, via="dm-button")
        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(interaction.response.send_message.await_args.kwargs.get("ephemeral"))

    async def test_component_click_opens_the_gate(self):
        import discord

        hold, member_role, guild = make_gate_roles()
        member = make_member(roles=[hold])
        member.guild = guild
        guild.get_member = lambda _id: member
        guild.fetch_member = AsyncMock(return_value=member)
        interaction = SimpleNamespace(
            type=discord.InteractionType.component,
            data={"custom_id": "policy:accept:900"},
            user=SimpleNamespace(id=500),
            response=SimpleNamespace(send_message=AsyncMock()),
        )
        config = {"policy_enabled": True, "policy_acceptances": {},
                  "policy_privacy_url": "x", "policy_terms_url": "y",
                  "policy_hold_role_id": 111, "policy_member_role_id": 222}
        with patch.object(self.bot, "record_policy_acceptance", AsyncMock(return_value="2026-09-09T00:00:00+00:00")), \
             patch.object(self.bot.client, "get_guild", lambda _id: guild), \
             patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value=config)):
            await self.bot.on_interaction(interaction)
        member.remove_roles.assert_awaited_once_with(hold, reason="Policy accepted")
        member.add_roles.assert_awaited_once_with(member_role, reason="Policy accepted")
        interaction.response.send_message.assert_awaited_once()

    async def test_unrelated_interactions_are_ignored(self):
        import discord

        interaction = SimpleNamespace(
            type=discord.InteractionType.application_command,
            data={"custom_id": "policy:accept:900"},
            user=SimpleNamespace(id=500),
            response=SimpleNamespace(send_message=AsyncMock()),
        )
        with patch.object(self.bot, "record_policy_acceptance", AsyncMock()) as record:
            await self.bot.on_interaction(interaction)
        record.assert_not_awaited()


class PolicyCardTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DISCORD_BOT_TOKEN", "test-only")
        import bot
        self.bot = bot
        self.config = {
            "policy_privacy_url": "https://holdings.thebabylon.hu/privacy",
            "policy_terms_url": "https://holdings.thebabylon.hu/terms",
        }

    def test_card_contains_policy_links_and_guild_scoped_button(self):
        view = self.bot._build_policy_card(self.config, guild_id=900)
        self.assertTrue(view.has_components_v2())
        payload = view.to_components()
        text = "\n".join(
            str(c) for c in payload
        )
        self.assertIn("policy:accept:900", text)
        self.assertIn("Privacy Policy", text)
        self.assertIn("Terms of Service", text)
