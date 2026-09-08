"""Reliability regressions; all provider and Discord calls are mocked."""
import asyncio
import json
import os
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import agent
from reliability import DEFAULT_CHAT_MODEL, chat_model, timeout_seconds
from tools.capital_rift import calculate_production_line


def response(text="Verified answer", calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=calls))])


def call(name, arguments="{}"):
    return SimpleNamespace(id="call-1", function=SimpleNamespace(name=name, arguments=arguments))


class AgentReliabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.wiki = AsyncMock(return_value=json.dumps({"data": {"results": [{"path": "Recipes/Iron.md", "excerpt": "2 iron"}]}}))
        self.create = AsyncMock(return_value=response())
        self.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)))
        for patcher in (
            patch.object(agent, "_client", self.client),
            patch.dict(agent.TOOL_IMPLS, {"capital_rift_wiki": self.wiki}),
            patch.dict(os.environ, {"AGENT_TURN_TIMEOUT_SECONDS": "2", "AGENT_TOOL_TIMEOUT_SECONDS": "1", "NVIDIA_REQUEST_TIMEOUT_SECONDS": "1"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_wiki_runs_before_model_that_never_calls_tools(self):
        async def answer(**kwargs):
            self.wiki.assert_awaited_once()
            tool_messages = [m for m in kwargs["messages"] if m["role"] == "tool"]
            self.assertIn("Recipes/Iron.md", tool_messages[0]["content"])
            return response()
        self.create.side_effect = answer
        history = [{"role": "user", "content": "Iron recipe"}]
        result = await agent.run_agent(history, "How many for 100/min?")
        self.assertEqual(result.status, "completed")
        self.assertIn("Iron recipe", self.wiki.call_args.kwargs["query"])
        self.assertEqual(len(history), 1)

    async def test_wiki_failure_is_visible_to_model(self):
        self.wiki.return_value = '{"data":{"error":"Not configured"}}'
        result = await agent.run_agent([], "hello")
        self.assertEqual(result.status, "completed")
        messages = self.create.call_args.kwargs["messages"]
        self.assertTrue(any("Not configured" in m.get("content", "") for m in messages))

    async def test_request_deadline_cancels_provider(self):
        cancelled = asyncio.Event()
        async def stalled(**kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        self.create.side_effect = stalled
        with patch.dict(os.environ, {"NVIDIA_REQUEST_TIMEOUT_SECONDS": "0.02"}):
            result = await asyncio.wait_for(agent.run_agent([], "hello"), 1)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(result.status, "timeout")
        self.assertIn("stopped", result.text)

    async def test_overall_deadline_includes_wiki(self):
        cancelled = asyncio.Event()
        async def stalled(**kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        self.wiki.side_effect = stalled
        with patch.dict(os.environ, {"AGENT_TURN_TIMEOUT_SECONDS": "0.02"}):
            result = await asyncio.wait_for(agent.run_agent([], "hello"), 1)
        self.assertEqual(result.status, "timeout")
        self.assertTrue(cancelled.is_set())
        self.create.assert_not_awaited()

    async def test_tool_timeout_recovers_with_error_result(self):
        cancelled = asyncio.Event()
        async def stalled(**kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        self.create.side_effect = [response(calls=[call("web_search")]), response("Search timed out")]
        with patch.dict(agent.TOOL_IMPLS, {"web_search": stalled}), patch.dict(os.environ, {"AGENT_TOOL_TIMEOUT_SECONDS": "0.02"}):
            result = await agent.run_agent([], "look this up")
        self.assertTrue(cancelled.is_set())
        self.assertEqual(result.text, "Search timed out")
        self.assertIn("timed out", self.create.call_args.kwargs["messages"][-1]["content"])

    async def test_invalid_arguments_never_execute_tool(self):
        for arguments in ("{bad", "[]", '"text"', "null"):
            with self.subTest(arguments=arguments):
                impl = AsyncMock()
                self.create.side_effect = [response(calls=[call("package_files", arguments)]), response()]
                with patch.dict(agent.TOOL_IMPLS, {"package_files": impl}):
                    result = await agent.run_agent([], "build")
                impl.assert_not_awaited()
                self.assertIsNone(result.zip_path)
                self.assertIn("error", self.create.call_args.kwargs["messages"][-1]["content"])

    async def test_calculator_json_string_works_through_agent_dispatch(self):
        arguments = json.dumps({
            "recipe_name": "Iron", "source_note": "Recipes/Iron.md",
            "target_output_per_minute": "75", "output_per_cycle": "2",
            "cycle_seconds": "4",
            "ingredients": '[{"name":"Ore","amount_per_cycle":"3"}]',
        })
        self.create.side_effect = [
            response(calls=[call("calculate_production_line", arguments)]), response("3 machines"),
        ]
        result = await agent.run_agent([], "Calculate iron production")
        self.assertEqual(result.text, "3 machines")
        tool_result = json.loads(self.create.call_args.kwargs["messages"][-1]["content"])
        self.assertEqual(tool_result["result"]["machinesRequired"], 3)
        self.assertEqual(tool_result["result"]["ingredients"][0]["requiredAtTargetPerMinute"], 112.5)

    async def test_failed_package_is_not_an_attachment(self):
        self.create.side_effect = [response(calls=[call("package_files")]), response()]
        with patch.dict(agent.TOOL_IMPLS, {"package_files": AsyncMock(side_effect=RuntimeError("private secret"))}):
            result = await agent.run_agent([], "build")
        self.assertIsNone(result.zip_path)
        self.assertNotIn("private secret", str(self.create.call_args.kwargs["messages"]))

    async def test_final_request_disables_tools_and_has_deadline(self):
        self.create.side_effect = [response(calls=[call("capital_rift_wiki", '{"action":"status"}')]), response("Finished")]
        result = await agent.run_agent([], "recipe", max_tool_rounds=1)
        self.assertEqual(result.text, "Finished")
        self.assertNotIn("tools", self.create.call_args.kwargs)
        self.assertNotIn("tool_choice", self.create.call_args.kwargs)
        messages = self.create.call_args.kwargs["messages"]
        self.assertFalse(any(m.get("tool_calls") or m["role"] == "tool" for m in messages))
        self.assertIn("Recipes/Iron.md", messages[-1]["content"])
        self.assertEqual(self.create.call_args.kwargs["timeout"], 1)

    async def test_final_request_timeout(self):
        async def answer(**kwargs):
            if "tools" not in kwargs:
                await asyncio.Event().wait()
            return response(calls=[call("capital_rift_wiki", '{"action":"status"}')])
        self.create.side_effect = answer
        with patch.dict(os.environ, {"NVIDIA_REQUEST_TIMEOUT_SECONDS": "0.02"}):
            result = await asyncio.wait_for(agent.run_agent([], "recipe", max_tool_rounds=1), 1)
        self.assertEqual(result.status, "timeout")

    async def test_external_cancellation_is_propagated(self):
        entered = asyncio.Event()
        async def stalled(**kwargs):
            entered.set()
            await asyncio.Event().wait()
        self.create.side_effect = stalled
        task = asyncio.create_task(agent.run_agent([], "hello"))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_logs_timings_completion_and_no_content(self):
        with self.assertLogs(agent.log, level="INFO") as logs:
            await agent.run_agent([], "secret user text")
        events = [json.loads(record.getMessage()) for record in logs.records]
        self.assertEqual(events[-1]["event"], "turn_finished")
        self.assertEqual(events[-1]["status"], "completed")
        self.assertTrue(any(e["event"] == "tool_finished" for e in events))
        self.assertEqual(len({e["turn_id"] for e in events}), 1)
        self.assertTrue(all(e["elapsed_ms"] >= 0 for e in events))
        self.assertNotIn("secret user text", str(logs.output))

    async def test_provider_error_is_safe(self):
        self.create.side_effect = RuntimeError("private provider details")
        with self.assertLogs(agent.log, level="INFO") as logs:
            result = await agent.run_agent([], "hello")
        self.assertEqual(result.status, "error")
        self.assertNotIn("private provider details", result.text + str(logs.output))


class CalculatorReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def calculate(self, **overrides):
        args = dict(recipe_name="Iron", source_note="Recipes/Iron.md", target_output_per_minute="75", output_per_cycle="2", cycle_seconds="4")
        args.update(overrides)
        return json.loads(await calculate_production_line(**args))

    async def test_json_ingredients_and_numeric_strings_match_native_values(self):
        data = [{"name": "Ore", "amount_per_cycle": "3"}]
        encoded = await self.calculate(ingredients=json.dumps(data))
        native = await self.calculate(ingredients=[{"name": "Ore", "amount_per_cycle": 3}])
        self.assertEqual(encoded, native)
        self.assertEqual(encoded["result"]["ingredients"][0]["requiredAtTargetPerMinute"], 112.5)

    async def test_invalid_ingredient_shapes_are_validation_errors(self):
        for value in ('{bad', '{}', 'null', {}, 1, False, ["Ore"], [{}], [{"name": "Ore"}], [{"name": None, "amount_per_cycle": 1}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.calculate(ingredients=value)

    async def test_invalid_numbers_are_rejected(self):
        for field in ("target_output_per_minute", "output_per_cycle", "cycle_seconds", "machine_speed_multiplier", "planned_utilization"):
            for value in (True, None, "nan", float("inf"), "-inf", 0, -1, "nope"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    await self.calculate(**{field: value})
        for value in (True, "nan", "inf", -1, None):
            with self.subTest(ingredient=value), self.assertRaises(ValueError):
                await self.calculate(ingredients=[{"name": "Ore", "amount_per_cycle": value}])

    async def test_zero_ingredients_allowed_and_extreme_values_fail_cleanly(self):
        result = await self.calculate(ingredients=[{"name": "Ore", "amount_per_cycle": "0"}])
        self.assertEqual(result["result"]["ingredients"][0]["requiredAtTargetPerMinute"], 0)
        with self.assertRaises(ValueError):
            await self.calculate(cycle_seconds=1e-320)


class SettingsTests(unittest.TestCase):
    def test_default_and_override(self):
        with patch.dict(os.environ, {"NVIDIA_CHAT_MODEL": " "}):
            self.assertEqual(chat_model(), DEFAULT_CHAT_MODEL)
        with patch.dict(os.environ, {"NVIDIA_CHAT_MODEL": " custom/model "}):
            self.assertEqual(chat_model(), "custom/model")

    def test_invalid_deadlines_are_rejected(self):
        for value in ("nan", "inf", "0", "-1", "oops"):
            with patch.dict(os.environ, {"TEST_DEADLINE": value}), self.assertRaises(ValueError):
                timeout_seconds("TEST_DEADLINE", 120)

    def test_async_client_has_no_hidden_retries(self):
        with patch.object(agent, "_client", None), patch.object(agent, "AsyncOpenAI") as factory, patch.dict(os.environ, {"NVIDIA_API_KEY": "test-only"}):
            agent._get_client()
        self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
        self.assertGreater(factory.call_args.kwargs["timeout"], 0)


class BotTimeoutDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_mention_stops_typing_sends_fallback_and_skips_history(self):
        with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "test-only"}), patch("dotenv.load_dotenv"):
            import bot
        state = {"typing": False}
        @asynccontextmanager
        async def typing():
            state["typing"] = True
            try:
                yield
            finally:
                state["typing"] = False
        channel = SimpleNamespace(id=123, typing=typing)
        message = SimpleNamespace(author=SimpleNamespace(bot=False), guild=None, channel=channel, mentions=[bot.client.user], content="hello")
        result = agent.AgentResult()
        result.text = "This request took too long, so I stopped it."
        result.status = "timeout"
        async def send(*args, **kwargs):
            self.assertFalse(state["typing"])
        with patch.object(bot, "run_agent", AsyncMock(return_value=result)), patch.object(bot.chat_history, "get_history", AsyncMock(return_value=[])), patch.object(bot.chat_history, "append_message", AsyncMock()) as save, patch.object(bot, "_send_agent_result", AsyncMock(side_effect=send)) as deliver, patch.object(bot.client, "_connection", SimpleNamespace(user=SimpleNamespace(id=999))):
            message.mentions = [bot.client.user]
            await bot.on_message(message)
        deliver.assert_awaited_once_with(channel, result, card=False, factory=False, factory_name="hello")
        save.assert_not_awaited()

    async def test_slash_command_sends_timeout_followup(self):
        with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "test-only"}), patch("dotenv.load_dotenv"):
            import bot
        interaction = SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock()))
        result = agent.AgentResult()
        result.status = "timeout"
        result.text = "This request took too long, so I stopped it."
        with patch.object(bot, "run_agent", AsyncMock(return_value=result)):
            await bot.ask.callback(interaction, "question")
        interaction.response.defer.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        self.assertEqual(kwargs["content"], result.text)
        self.assertIn("view", kwargs)
        self.assertEqual(kwargs["view"].children[0].label, "Send logs")


class FactoryRoutingTests(unittest.TestCase):
    def test_only_factory_planning_requests_opt_into_cards(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "test-only"}), patch("dotenv.load_dotenv"):
            import bot
        self.assertTrue(bot._wants_factory_card("How do I build a computer factory?"))
        self.assertTrue(bot._wants_factory_card("set up a production line for iron bars"))
        self.assertFalse(bot._wants_factory_card("What is a computer?"))
        self.assertFalse(bot._wants_factory_card("Tell me a joke about factories"))


class DirectWikiLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_fuzzy_results_do_not_become_false_exact_matches(self):
        import json
        from unittest.mock import AsyncMock, patch
        with patch.dict(__import__('os').environ, {"DISCORD_BOT_TOKEN": "test-only"}), patch("dotenv.load_dotenv"):
            import bot
        search = AsyncMock(return_value=json.dumps({"data": {"results": [{"title": "Capital Rift", "path": "Capital Rift.md"}]}}))
        with patch("bot.capital_rift_wiki", search):
            note, error = await bot._capital_rift_note("Definitely Not An Item", "item")
        self.assertIsNone(note)
        self.assertIn("No exact item named", error)
