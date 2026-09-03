import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import capital_rift
from tools.obsidian import obsidian_read, obsidian_search


class ObsidianCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_tools_use_secure_shared_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault = root / "vault"
            notes = vault / "Notes"
            notes.mkdir(parents=True)
            (notes / "Compatibility.md").write_text(
                "# Compatibility\n\nThe calibration code is violet-crystal-731.\n",
                encoding="utf-8",
            )
            environment = {
                "CAPITAL_RIFT_VAULT_PATH": "",
                "OBSIDIAN_VAULT_PATH": str(vault),
                "CAPITAL_RIFT_INDEX_PATH": str(root / "index" / "wiki.db"),
                "CAPITAL_RIFT_VAULT_REFRESH_SECONDS": "0",
            }

            capital_rift._WIKI_INDEX = None
            try:
                with patch.dict(os.environ, environment, clear=False):
                    search = json.loads(
                        await obsidian_search("violet crystal calibration")
                    )
                    note = await obsidian_read("Notes/Compatibility")
            finally:
                capital_rift._WIKI_INDEX = None

            self.assertEqual(search["count"], 1)
            self.assertEqual(
                search["results"][0]["filename"],
                "Notes/Compatibility.md",
            )
            self.assertIn("violet-crystal-731", note)


if __name__ == "__main__":
    unittest.main()
