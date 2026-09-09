"""Offline factory regressions using local wiki snapshots and malformed graphs."""
import asyncio
from contextlib import asynccontextmanager
from fractions import Fraction
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from knowledge.obsidian_vault import ObsidianVaultIndex
from response_cards import FactoryPlanView, build_factory_views, send_factory_plan
from tools.factory_calculator import (
    FactoryError, FactoryRequest, calculate_factory, full_factory_request,
    parse_factory_request, parse_recipe, plan_factory,
)

FIXTURES = json.loads((Path(__file__).parent / "fixtures/factory_wiki.json").read_text(encoding="utf-8"))


def note(name, ingredients=None, *, output=1, rate=10, machine="Press"):
    recipe = ""
    if ingredients is not None:
        recipe = (
            f"recipe_machine: '[[{machine}]]'\nrecipe_output_quantity: {output}\n"
            f"recipe_rate_per_minute: {rate}\n"
        )
    body = "Raw material."
    if ingredients is not None:
        body = "## Recipe\n\n### Make " + name + "\n\n#### Ingredients\n\n| Quantity | Item |\n|---:|---|\n"
        body += "\n".join(f"| {qty} | [[{item}]] |" for item, qty in ingredients)
    return {
        "path": f"Items/{name}.md", "title": name,
        "content": f"---\nname: {name}\nsource: https://wiki.capitalrift.com/items/{name.lower()}/\n{recipe}---\n# {name}\n\n{body}\n"
    }


def text_of(views):
    return "\n".join(c["content"] for view in views for c in view.to_components()[0]["components"] if c["type"] == 10)


class RequestTests(unittest.TestCase):
    def test_supported_rates_and_plural_names(self):
        for text, name, rate in [
            ("How do I make 1 Computer per minute from raw components?", "Computer", Fraction(1)),
            ("How do I make a factory for Bucket Wheel Excavators at 0.1 per minute?", "Bucket Wheel Excavators", Fraction(1, 10)),
            ("Build me the full production chain for 10 computers per hour.", "computers", Fraction(1, 6)),
            ("0.1 Bucket Wheel Excavators/min", "Bucket Wheel Excavators", Fraction(1, 10)),
            ("Computer capable of 1 per minute", "Computer", Fraction(1)),
            ("Computer at .5/hr", "Computer", Fraction(1, 120)),
        ]:
            with self.subTest(text=text):
                self.assertTrue(full_factory_request(text))
                self.assertEqual(parse_factory_request(text), FactoryRequest(name, rate))

    def test_no_silent_default_or_invalid_scale(self):
        with self.assertRaisesRegex(FactoryError, "Specify a scale"):
            calculate_factory(FIXTURES, parse_factory_request("full factory for Computer"))
        for text in ("Computer at 0/min", "Computer at -1/min", "Computer at 1000001/min", "Computer 1/min 2/hour"):
            with self.subTest(text=text), self.assertRaises(FactoryError):
                parse_factory_request(text)
        self.assertFalse(full_factory_request("Computer"))


class CalculatorTests(unittest.TestCase):
    def test_computer_one_per_minute(self):
        plan = calculate_factory(FIXTURES, FactoryRequest("Computer", Fraction(1)))
        self.assertTrue(plan.complete, plan.issues)
        self.assertEqual(len(plan.stages), 17)
        stages = {stage.recipe.name: stage for stage in plan.stages}
        self.assertEqual(stages["Computer"].machines, 100)
        self.assertEqual(stages["RAM Stick"].required, 2)
        self.assertEqual(stages["Motherboard"].required, 1)
        self.assertEqual(plan.machine_totals, {
            "Electronics Bench": 243, "Manufacturing Press": 25, "Furnace": 33,
            "Chip Fab": 301, "Chemical Plant": 73, "Metal Shop": 14,
        })
        self.assertEqual({s.recipe.name: s.required for s in plan.inputs},
                         {"Iron Ore": Fraction(29, 3), "Quartz": 152, "Concrete": 6, "Copper Ore": 11})
        self.assertEqual(plan.stages[-1].recipe.name, "Computer")

    def test_excavator_fractional_scale(self):
        plan = calculate_factory(FIXTURES, FactoryRequest("Bucket Wheel Excavators", Fraction(1, 10)))
        self.assertTrue(plan.complete, plan.issues)
        self.assertEqual(len(plan.stages), 30)
        self.assertEqual(plan.stages[-1].machines, 84)
        self.assertEqual(sum(plan.machine_totals.values()), 535)
        self.assertEqual({s.recipe.name: s.required for s in plan.inputs}, {
            "Iron Ore": Fraction(1045, 6), "Quartz": Fraction(106, 5),
            "Copper Ore": Fraction(191, 50), "Concrete": Fraction(13, 15),
            "Wool": Fraction(4, 5), "Lithium Ore": Fraction(2, 5),
        })

    def test_hourly_conversion_scales_every_input(self):
        minute = calculate_factory(FIXTURES, FactoryRequest("Computer", Fraction(1)))
        hour = calculate_factory(FIXTURES, parse_factory_request("10 computers per hour"))
        self.assertEqual(hour.stages[-1].machines, 17)
        base = {s.recipe.name: s.required for s in minute.inputs}
        for stage in hour.inputs:
            self.assertEqual(stage.required, base[stage.recipe.name] / 6)

    def test_shared_demand_aggregated_before_rounding_and_batch_ratio(self):
        notes = [
            note("Final", [("A", 1), ("B", 1)]), note("A", [("Shared", 1)]),
            note("B", [("Shared", 1)]), note("Shared", [("Ore", 6)], output=2, rate=10),
            note("Ore"), note("Press"),
        ]
        plan = calculate_factory(notes, FactoryRequest("Final", Fraction(3)))
        shared = next(s for s in plan.stages if s.recipe.name == "Shared")
        self.assertEqual(shared.required, 6)
        self.assertEqual(shared.machines, 1)
        self.assertEqual(plan.inputs[0].required, 18)
        self.assertEqual(plan.machine_totals, {"Press": 4})

    def test_missing_note_retains_external_demand(self):
        plan = calculate_factory([note("Final", [("Unknown", 2)])], FactoryRequest("Final", Fraction(3)))
        self.assertFalse(plan.complete)
        self.assertEqual(plan.inputs[0].required, 6)
        self.assertFalse(plan.inputs[0].recipe.raw)
        self.assertIn("Wiki note/recipe missing", " ".join(plan.issues))

    def test_missing_rate_keeps_upstream_math_without_inventing_machines(self):
        plan = calculate_factory([note("Final", [("Ore", 2)], rate="nan"), note("Ore")],
                                 FactoryRequest("Final", Fraction(3)))
        self.assertIsNone(plan.stages[0].machines)
        self.assertEqual(plan.inputs[0].required, 6)
        self.assertFalse(plan.complete)

    def test_bad_output_or_ingredient_quantity_stops_branch(self):
        for n in (note("Final", [("Ore", "?")]), note("Final", [("Ore", 2)], output=0)):
            plan = calculate_factory([n, note("Ore")], FactoryRequest("Final", Fraction(3)))
            self.assertFalse(plan.complete)
            self.assertEqual(plan.inputs, [])

    def test_name_only_metadata_is_not_a_quantified_recipe(self):
        n = note("Final", [])
        n["content"] = n["content"].replace("## Recipe", "ingredients:\n  - '[[Ore]]'\n## Recipe")
        self.assertEqual(parse_recipe(n).ingredients, [])
        self.assertIn("Ingredient table incomplete", " ".join(parse_recipe(n).issues))

    def test_cycle_is_reported_without_partial_totals(self):
        with self.assertRaisesRegex(FactoryError, "cycle"):
            calculate_factory([note("A", [("B", 1)]), note("B", [("A", 1)])], FactoryRequest("A", Fraction(1)))

    def test_missing_target_and_ambiguous_names_do_not_fuzzy_match(self):
        for notes, name in [(FIXTURES, "Not Computer"), ([note("A"), dict(note("A"), path="Other/A.md")], "A")]:
            with self.assertRaises(FactoryError):
                calculate_factory(notes, FactoryRequest(name, Fraction(1)))

    def test_truncation_and_alternative_recipes_are_marked(self):
        for n in [dict(note("A", [("Ore", 1)]), truncated=True),
                  dict(note("A", [("Ore", 1)]), content=note("A", [("Ore", 1)])["content"] + "\n### Alternative\n")]:
            plan = calculate_factory([n, note("Ore")], FactoryRequest("A", Fraction(1)))
            self.assertFalse(plan.complete)
            self.assertEqual(plan.inputs, [])
            self.assertIsNone(plan.stages[0].machines)

    def test_aliases_resolve_real_item_not_display_label(self):
        plan = calculate_factory([note("A", [("Ore#Source|ore alias", 2)]), note("Ore")], FactoryRequest("A", Fraction(1)))
        self.assertEqual(plan.inputs[0].recipe.name, "Ore")
        self.assertEqual(plan.inputs[0].required, 2)

    def test_placement_comes_from_machine_not_finished_item(self):
        final = note("Final", [("Ore", 1)])
        final["content"] = final["content"].replace("name: Final", "name: Final\nplacement: Outdoors only")
        machine = note("Press")
        machine["content"] = machine["content"].replace("name: Press", "name: Press\nplacement: Requires indoor space")
        plan = calculate_factory([final, machine, note("Ore")], FactoryRequest("Final", Fraction(1)))
        self.assertEqual(plan.placements, [("Press", "Requires indoor space")])
        self.assertNotIn("Outdoors only", text_of(build_factory_views(plan)))

    def test_depth_limit_is_explicit(self):
        notes = [note(f"Item{i}", [(f"Item{i + 1}", 1)]) for i in range(67)]
        with self.assertRaisesRegex(FactoryError, "limit"):
            calculate_factory(notes, FactoryRequest("Item0", Fraction(1)))


class LayoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_mobile_pages_keep_all_stages_and_clickable_links(self):
        plan = calculate_factory(FIXTURES, FactoryRequest("Bucket Wheel Excavators", Fraction(1, 10)))
        views = build_factory_views(plan)
        text = text_of(views)
        self.assertGreater(len(views), 1)
        for view in views:
            self.assertTrue(view.has_components_v2())
            self.assertLessEqual(view.content_length(), 4000)
            self.assertLessEqual(view.total_children_count, 40)
            self.assertLessEqual(len(view.to_components()[0]["components"][2]["content"]), 3000)
        for stage in plan.stages + plan.inputs:
            self.assertIn(f"]({stage.recipe.source})", text)
        self.assertNotIn("See source", text)
        self.assertNotIn("factory parcel", text)
        self.assertIn("spare capacity", text)
        send = AsyncMock()
        await send_factory_plan(send, plan, ephemeral=True)
        self.assertEqual(send.await_count, 1)
        for call in send.await_args_list:
            self.assertEqual(call.kwargs["allowed_mentions"].to_dict()["parse"], [])
            self.assertTrue(call.kwargs["ephemeral"])
            self.assertNotIn("content", call.kwargs)
            self.assertNotIn("embed", call.kwargs)

    async def test_partial_totals_and_missing_data_visible(self):
        plan = calculate_factory([note("A", [("Unknown", 1)])], FactoryRequest("A", Fraction(1)))
        text = text_of(build_factory_views(plan))
        self.assertIn("Partial plan", text)
        self.assertIn("known machines", text)
        self.assertIn("Missing wiki data", text)
        self.assertIn("source link missing", text)

    async def test_overview_is_short_and_detail_buttons_edit_in_place(self):
        plan = calculate_factory(FIXTURES, FactoryRequest("Bucket Wheel Excavators", Fraction(1, 10)))
        send = AsyncMock()
        await send_factory_plan(send, plan)
        send.assert_awaited_once()
        view = send.call_args.kwargs["view"]
        overview = text_of([view])
        self.assertLess(len(overview), 850)
        self.assertNotIn("Iron Ore", overview)
        self.assertIn("Final assembly", overview)
        buttons = [item for item in view.walk_children() if hasattr(item, "label")]
        stages = next(b for b in buttons if b.label == "Stages")
        interaction = SimpleNamespace(response=SimpleNamespace(edit_message=AsyncMock()), message=AsyncMock())
        await stages.callback(interaction)
        changed = interaction.response.edit_message.call_args.kwargs["view"]
        self.assertIn("Stages · 1/10", text_of([changed]))
        self.assertIn("per minute total", text_of([changed]))
        self.assertIn("Supplies:", text_of([changed]))
        self.assertNotIn("/ min each", text_of([changed]))
        self.assertLessEqual(changed.content_length(), 4000)
        next_button = next(b for b in changed.walk_children() if getattr(b, "label", None) == "Next")
        await next_button.callback(interaction)
        page_two = interaction.response.edit_message.call_args.kwargs["view"]
        self.assertIn("Stages · 2/10", text_of([page_two]))
        home = next(b for b in page_two.walk_children() if getattr(b, "label", None) == "Overview")
        await home.callback(interaction)
        self.assertIn("Final assembly", text_of([interaction.response.edit_message.call_args.kwargs["view"]]))
        send.assert_awaited_once()

    async def test_expiration_disables_controls_and_explains_how_to_reopen(self):
        plan = calculate_factory(FIXTURES, FactoryRequest("Computer", Fraction(1)))
        view = FactoryPlanView(plan)
        view.message = AsyncMock()
        await view.on_timeout()
        view.message.edit.assert_awaited_once()
        for item in view.walk_children():
            if hasattr(item, "disabled"):
                self.assertTrue(item.disabled)
        self.assertIn("Controls expired", json.dumps(view.to_components()))


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_and_planner_do_not_truncate_long_recipes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            vault.mkdir()
            for n in [note("A", [("Ore", 2)]), note("Ore"), note("Press")]:
                content = n["content"]
                if n["title"] == "A":
                    content = content.replace("## Recipe", "<!--" + "padding" * 2000 + "-->\n## Recipe")
                (vault / (n["title"] + ".md")).write_text(content, encoding="utf-8")
            index = ObsidianVaultIndex(str(vault), str(root / "index.db"), refresh_seconds=0)
            before = {p.name: p.read_bytes() for p in vault.iterdir()}
            with patch("tools.capital_rift._get_wiki_index", return_value=index):
                plan = await plan_factory(FactoryRequest("A", Fraction(3)))
            self.assertEqual(plan.inputs[0].required, 6)
            self.assertEqual(before, {p.name: p.read_bytes() for p in vault.iterdir()})

    async def test_factory_and_ask_use_calculator_without_model(self):
        with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "test-only"}), patch("dotenv.load_dotenv"):
            import bot
        plan = calculate_factory(FIXTURES, FactoryRequest("Computer", Fraction(1)))
        for command, kwargs in [(bot.factory.callback, {"item": "Computer", "amount": 1.0}),
                                (bot.ask.callback, {"question": "Build me the full production chain for 10 computers per hour"})]:
            interaction = SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock()))
            with patch.object(bot, "plan_factory", AsyncMock(return_value=plan)) as calc, patch.object(bot, "run_agent", AsyncMock()) as model:
                await command(interaction, **kwargs)
            calc.assert_awaited_once()
            model.assert_not_awaited()
            self.assertTrue(interaction.followup.send.call_args.kwargs["view"].has_components_v2())

    async def test_factory_options_expose_item_and_optional_numeric_amount(self):
        import bot
        params = {p.name: p for p in bot.factory.parameters}
        self.assertEqual(set(params), {"item", "amount"})
        self.assertTrue(params["item"].required)
        self.assertFalse(params["amount"].required)
        self.assertEqual(params["amount"].type.value, 10)
        self.assertGreater(params["amount"].min_value, 0)
        plan = calculate_factory(FIXTURES, FactoryRequest("Bucket Wheel Excavators", Fraction(1, 10)))
        with patch.object(bot, "plan_factory", AsyncMock(return_value=plan)) as calc:
            result = await bot._deterministic_factory_result("Bucket Wheel Excavators", amount=0.1)
        calc.assert_awaited_once_with(FactoryRequest("Bucket Wheel Excavators", Fraction(1, 10)))
        self.assertIs(result.factory_plan, plan)

    async def test_ordinary_factory_keeps_original_card_path(self):
        import bot
        with patch.object(bot, "_capital_rift_note", AsyncMock(return_value=(FIXTURES[0], None))), patch.object(bot, "plan_factory", AsyncMock()) as calc:
            result = await bot._deterministic_factory_result("Computer")
        calc.assert_not_awaited()
        self.assertIsNone(result.factory_plan)
        self.assertIn("exact_note", json.loads(result.wiki_context))

    async def test_calculator_timeout_preserves_diagnostics_button(self):
        import bot
        async def stall(request):
            await asyncio.sleep(10)
        with patch.object(bot, "plan_factory", side_effect=stall), patch.dict(os.environ, {"AGENT_TURN_TIMEOUT_SECONDS": "0.01"}):
            result = await bot._deterministic_factory_result("Computer at 1/min")
        self.assertEqual(result.status, "timeout")
        channel = SimpleNamespace(send=AsyncMock())
        await bot._send_agent_result(channel, result, card=True, factory=True)
        self.assertEqual(channel.send.call_args.kwargs["view"].children[0].label, "Send logs")

    async def test_natural_language_mention_routes_to_full_factory(self):
        import bot
        @asynccontextmanager
        async def typing():
            yield
        channel = SimpleNamespace(id=123, send=AsyncMock(), typing=typing)
        plan = calculate_factory(FIXTURES, FactoryRequest("Computer", Fraction(1)))
        with patch.object(bot.client, "_connection", SimpleNamespace(user=SimpleNamespace(id=999))), patch.object(bot, "plan_factory", AsyncMock(return_value=plan)) as calc, patch.object(bot, "run_agent", AsyncMock()) as model, patch.object(bot.chat_history, "get_history", AsyncMock(return_value=[])):
            message = SimpleNamespace(author=SimpleNamespace(bot=False), guild=None, channel=channel,
                                      mentions=[bot.client.user], content="<@999> How do I make 1 Computer per minute from raw components?")
            await bot.on_message(message)
        calc.assert_awaited_once()
        model.assert_not_awaited()
        self.assertTrue(channel.send.call_args.kwargs["view"].has_components_v2())
