import asyncio
import json
import os
import tempfile
import unittest

from moderation import store


class GuildConfigStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_data_dir = store.DATA_DIR
        self.original_config_path = store.CONFIG_PATH
        self.original_cache = store._cache
        self.original_lock = store._lock

        store.DATA_DIR = self.temp_dir.name
        store.CONFIG_PATH = os.path.join(self.temp_dir.name, "guild_config.json")
        store._cache = {}
        store._lock = asyncio.Lock()

    async def asyncTearDown(self):
        store.DATA_DIR = self.original_data_dir
        store.CONFIG_PATH = self.original_config_path
        store._cache = self.original_cache
        store._lock = self.original_lock
        self.temp_dir.cleanup()

    async def test_defaults_include_server_administration_settings(self):
        config = await store.get_guild_config(123)
        self.assertFalse(config["setup_complete"])
        self.assertIsNone(config["admin_role_id"])
        self.assertIsNone(config["market_channel_id"])
        self.assertFalse(config["market_alerts_enabled"])

    async def test_updates_are_persisted_atomically(self):
        await store.update_guild_config(
            123,
            setup_complete=True,
            admin_role_id=456,
            market_channel_id=789,
        )

        self.assertTrue(os.path.exists(store.CONFIG_PATH))
        self.assertFalse(os.path.exists(f"{store.CONFIG_PATH}.tmp"))
        with open(store.CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["123"]["admin_role_id"], 456)
        self.assertEqual(saved["123"]["market_channel_id"], 789)

    async def test_unknown_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            await store.update_guild_config(123, misspelled_setting=True)

    async def test_reset_preserves_warning_history(self):
        await store.update_guild_config(123, setup_complete=True, admin_role_id=456)
        await store.add_warning(123, 999)
        reset = await store.reset_guild_config(123, preserve_warnings=True)

        self.assertFalse(reset["setup_complete"])
        self.assertIsNone(reset["admin_role_id"])
        self.assertEqual(reset["warnings"], {"999": 1})
