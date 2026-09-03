import json
import tempfile
import unittest
from pathlib import Path

from knowledge.obsidian_vault import ObsidianVaultIndex, VaultError
from tools.capital_rift import calculate_production_line


class ObsidianVaultIndexTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.vault = root / "vault"
        self.vault.mkdir()
        (self.vault / ".obsidian").mkdir()
        (self.vault / ".obsidian" / "workspace.md").write_text(
            "private workspace state", encoding="utf-8"
        )
        (self.vault / "Recipes").mkdir()
        (self.vault / "Recipes" / "Iron Plate.md").write_text(
            "# Iron Plate\n\nAn assembler makes 2 iron plates every 4 seconds "
            "using 3 iron ingots.",
            encoding="utf-8",
        )
        (self.vault / "Buildings.md").write_text(
            "# Factory Buildings\n\nAssemblers process manufactured recipes.",
            encoding="utf-8",
        )
        self.index = ObsidianVaultIndex(
            str(self.vault),
            str(root / "index" / "wiki.db"),
            refresh_seconds=0,
        )

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_indexes_markdown_and_excludes_obsidian_metadata(self):
        status = await self.index.sync()
        self.assertEqual(status["totalNotes"], 2)

        results = await self.index.search("iron plate")
        self.assertEqual(results[0].path, "Recipes/Iron Plate.md")
        self.assertEqual(results[0].title, "Iron Plate")

    async def test_reads_only_relative_markdown_inside_vault(self):
        note = await self.index.read_note("Recipes/Iron Plate.md")
        self.assertIn("3 iron ingots", note["content"])
        self.assertFalse(note["truncated"])

        with self.assertRaises(VaultError):
            await self.index.read_note("../outside.md")

    async def test_refreshes_changed_notes(self):
        await self.index.sync()
        note_path = self.vault / "Recipes" / "Iron Plate.md"
        note_path.write_text(
            "# Iron Plate\n\nA revised recipe uses hematite crystals.",
            encoding="utf-8",
        )
        await self.index.sync(force=True)

        results = await self.index.search("hematite")
        self.assertEqual(results[0].path, "Recipes/Iron Plate.md")


class ProductionCalculatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_calculates_machine_and_ingredient_rates(self):
        result = json.loads(
            await calculate_production_line(
                recipe_name="Iron Plate",
                source_note="Recipes/Iron Plate.md",
                target_output_per_minute=75,
                output_per_cycle=2,
                cycle_seconds=4,
                ingredients=[{"name": "Iron Ingot", "amount_per_cycle": 3}],
            )
        )

        calculation = result["result"]
        self.assertTrue(result["deterministic"])
        self.assertEqual(calculation["outputPerMachinePerMinute"], 30)
        self.assertEqual(calculation["exactMachines"], 2.5)
        self.assertEqual(calculation["machinesRequired"], 3)
        self.assertEqual(calculation["outputAtFullCapacityPerMinute"], 90)
        self.assertEqual(
            calculation["ingredients"][0]["requiredAtTargetPerMinute"], 112.5
        )
        self.assertEqual(
            calculation["ingredients"][0]["fullCapacityPerMinute"], 135
        )

    async def test_rejects_missing_wiki_source(self):
        with self.assertRaises(ValueError):
            await calculate_production_line(
                recipe_name="Unknown",
                source_note="",
                target_output_per_minute=10,
                output_per_cycle=1,
                cycle_seconds=5,
            )
