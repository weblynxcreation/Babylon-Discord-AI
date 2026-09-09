import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from moderation import store


def make_role(role_id, *, name="Role", managed=False, is_default=False, position=1):
    return SimpleNamespace(
        id=role_id, name=name, managed=managed, is_default=lambda: is_default,
        position=position,
    )


def make_member(top_position=10, manage_roles=True, bot=False):
    top_role = SimpleNamespace(name="BotTop", position=top_position)
    return SimpleNamespace(
        bot=bot, top_role=top_role,
        guild_permissions=SimpleNamespace(manage_roles=manage_roles),
        add_roles=AsyncMock(), remove_roles=AsyncMock(),
    )


class ReactionRoleConfigStoreTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_mappings_round_trip_through_disk(self):
        mappings = [{"channel_id": "1", "message_id": "2", "emoji": "👍", "role_id": "3"}]
        await store.update_guild_config(900, reaction_roles=mappings)
        store._cache = {}  # force a reload from disk
        store._load()
        config = await store.get_guild_config(900)
        self.assertEqual(config["reaction_roles"], mappings)

    async def test_defaults_start_with_no_mappings(self):
        config = await store.get_guild_config(901)
        self.assertEqual(config["reaction_roles"], [])


class EmojiMatchingTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DISCORD_BOT_TOKEN", "test-only")
        import bot
        self.bot = bot

    def test_unicode_emoji_matches_exactly(self):
        self.assertTrue(self.bot._emoji_matches("👍", "👍"))
        self.assertFalse(self.bot._emoji_matches("👍", "👎"))

    def test_custom_emoji_matches_by_id_across_names(self):
        self.assertTrue(self.bot._emoji_matches("<:hey:123>", "<:hi:123>"))
        self.assertFalse(self.bot._emoji_matches("<:hey:123>", "<:hi:124>"))

    def test_empty_never_matches(self):
        self.assertFalse(self.bot._emoji_matches("", "👍"))
        self.assertFalse(self.bot._emoji_matches("👍", ""))


class MappingLookupTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DISCORD_BOT_TOKEN", "test-only")
        import bot
        self.bot = bot
        self.config = {
            "reaction_roles": [
                {"channel_id": "10", "message_id": "20", "emoji": "👍", "role_id": "30"},
                {"channel_id": "10", "message_id": "20", "emoji": "<:gg:99>", "role_id": "31"},
            ]
        }

    def test_finds_entry_by_channel_message_and_emoji(self):
        entry = self.bot._find_reaction_mapping(self.config, 10, 20, "👍")
        self.assertEqual(entry["role_id"], "30")

    def test_custom_emoji_found_by_id(self):
        entry = self.bot._find_reaction_mapping(self.config, 10, 20, "<:other:99>")
        self.assertEqual(entry["role_id"], "31")

    def test_miss_returns_none(self):
        self.assertIsNone(self.bot._find_reaction_mapping(self.config, 10, 21, "👍"))
        self.assertIsNone(self.bot._find_reaction_mapping(self.config, 11, 20, "👍"))


class RoleValidationTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DISCORD_BOT_TOKEN", "test-only")
        import bot
        self.bot = bot

    def _issues(self, role, member):
        return self.bot._reaction_role_issues(role, member)

    def test_valid_role_has_no_issues(self):
        role = make_role(1, position=5)
        me = make_member(top_position=10)
        self.assertEqual(self._issues(role, me), [])

    def test_everyone_managed_and_high_roles_are_rejected(self):
        me = make_member(top_position=10)
        self.assertTrue(self._issues(make_role(1, is_default=True), me))
        self.assertTrue(self._issues(make_role(2, managed=True), me))
        self.assertTrue(self._issues(make_role(3, position=10), me))

    def test_missing_manage_roles_is_reported(self):
        me = make_member(top_position=10, manage_roles=False)
        self.assertTrue(self._issues(make_role(4, position=5), me))


class MessageRefParsingTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DISCORD_BOT_TOKEN", "test-only")
        import bot
        self.bot = bot

    def test_message_link_yields_channel_and_message(self):
        channel_id, message_id = self.bot._parse_message_ref(
            "https://discord.com/channels/5/100/200"
        )
        self.assertEqual((channel_id, message_id), (100, 200))

    def test_bare_id_yields_message_only(self):
        self.assertEqual(self.bot._parse_message_ref("200"), (None, 200))

    def test_garbage_yields_nothing(self):
        self.assertEqual(self.bot._parse_message_ref("nope"), (None, None))


class RawReactionHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        os.environ.setdefault("DISCORD_BOT_TOKEN", "test-only")
        import bot
        self.bot = bot

    def _payload(self, *, user_id=777, emoji="👍"):
        return SimpleNamespace(
            guild_id=900, channel_id=10, message_id=20, user_id=user_id,
            emoji=emoji, member=None,
        )

    async def test_reaction_add_grants_mapped_role(self):
        role = make_role(30, position=5)
        member = make_member(top_position=10)
        guild = SimpleNamespace(me=make_member(top_position=10), get_role=lambda _id: role,
                                get_member=lambda _id: member)
        payload = self._payload()
        payload.member = member
        with patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value={
            "reaction_roles": [{"channel_id": "10", "message_id": "20", "emoji": "👍", "role_id": "30"}],
        })), patch.object(self.bot.client, "get_guild", lambda _id: guild):
            await self.bot._handle_raw_reaction(payload, add=True)
        member.add_roles.assert_awaited_once()
        args, kwargs = member.add_roles.await_args
        self.assertEqual(args[0], role)
        self.assertEqual(kwargs["reason"], "Reaction role")

    async def test_reaction_remove_revokes_mapped_role(self):
        role = make_role(30, position=5)
        member = make_member(top_position=10)
        guild = SimpleNamespace(me=make_member(top_position=10), get_role=lambda _id: role,
                                get_member=lambda _id: member)
        payload = self._payload()
        payload.member = member
        with patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value={
            "reaction_roles": [{"channel_id": "10", "message_id": "20", "emoji": "👍", "role_id": "30"}],
        })), patch.object(self.bot.client, "get_guild", lambda _id: guild):
            await self.bot._handle_raw_reaction(payload, add=False)
        member.remove_roles.assert_awaited_once()

    async def test_unmapped_or_unsafe_roles_are_ignored(self):
        member = make_member(top_position=10)
        high_role = make_role(30, position=50)  # above the bot: must not be granted
        guild = SimpleNamespace(me=make_member(top_position=10), get_role=lambda _id: high_role,
                                get_member=lambda _id: member)
        payload = self._payload()
        payload.member = member
        with patch.object(self.bot.mod_store, "get_guild_config", AsyncMock(return_value={
            "reaction_roles": [{"channel_id": "10", "message_id": "20", "emoji": "👍", "role_id": "30"}],
        })), patch.object(self.bot.client, "get_guild", lambda _id: guild):
            await self.bot._handle_raw_reaction(payload, add=True)  # must not raise
        member.add_roles.assert_not_awaited()

    async def test_own_reactions_are_ignored(self):
        payload = self._payload(user_id=1)
        with patch.object(self.bot.client._connection, "user", SimpleNamespace(id=1)), \
             patch.object(self.bot.mod_store, "get_guild_config", AsyncMock()) as get_config:
            await self.bot._handle_raw_reaction(payload, add=True)
        get_config.assert_not_awaited()
