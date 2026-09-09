"""Regression coverage for issues #17, #18, #16, and #7; no live services."""
import asyncio
from contextlib import asynccontextmanager
from fractions import Fraction
import io
import json
import logging
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import agent
from card_primitives import CardError, add_actions, build_card, paginate_text
import discord
from observability import (
    configure_logging, current_trace, diagnostic_excerpt, mark_delivery, new_trace,
)
from response_cards import build_response_views
from response_lifecycle import bounded_command, bounded_message, recover_response, typing_scope
from tools import codegen, web_search


def interaction():
    response = SimpleNamespace(is_done=lambda: True, send_message=AsyncMock(), defer=AsyncMock())
    return SimpleNamespace(response=response, edit_original_response=AsyncMock(),
                           delete_original_response=AsyncMock(), followup=SimpleNamespace(send=AsyncMock()),
                           original_response=AsyncMock(return_value=SimpleNamespace(flags=SimpleNamespace(loading=True))))


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = patch.dict("os.environ", {
            "DISCORD_RESPONSE_TIMEOUT_SECONDS": "0.04", "DISCORD_RECOVERY_TIMEOUT_SECONDS": "0.02",
        })
        self.settings.start()
        self.addCleanup(self.settings.stop)

    async def test_deferred_timeout_cancels_work_clears_original_and_next_request_works(self):
        stopped = asyncio.Event()
        @bounded_command
        async def command(target, *, stall):
            if stall:
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()
            else:
                await target.followup.send(content="Ready")
                mark_delivery()
        first = interaction()
        await command(first, stall=True)
        self.assertTrue(stopped.is_set())
        self.assertIn("too long", first.edit_original_response.call_args.kwargs["content"])
        second = interaction()
        await command(second, stall=False)
        second.followup.send.assert_awaited_once()
        second.edit_original_response.assert_not_awaited()

    async def test_error_response_does_not_expose_exception_text(self):
        @bounded_command
        async def command(target):
            raise RuntimeError("private prompt secret-token")
        target = interaction()
        with self.assertLogs("discord-ai-agent.responses", level="INFO") as capture:
            await command(target)
        self.assertNotIn("private prompt", str(capture.output) + str(target.edit_original_response.call_args))
        self.assertIn("response_failed", str(capture.output))
        target.edit_original_response.assert_awaited_once()

    async def test_external_cancellation_acknowledged_and_propagated(self):
        entered = asyncio.Event()
        @bounded_command
        async def command(target):
            entered.set()
            await asyncio.Event().wait()
        target = interaction()
        task = asyncio.create_task(command(target))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIn("cancelled", target.edit_original_response.call_args.kwargs["content"])

    async def test_missing_followup_is_detected_and_resolved(self):
        @bounded_command
        async def command(target):
            pass
        target = interaction()
        with self.assertLogs("discord-ai-agent.responses", level="INFO") as capture:
            await command(target)
        self.assertIn("unresolved_defer", str(capture.output))
        target.edit_original_response.assert_awaited_once()

    async def test_failed_recovery_edit_deletes_loading_response(self):
        target = interaction()
        target.edit_original_response.side_effect = RuntimeError("Network failure")
        await recover_response(target, "Retry", interaction=True)
        target.delete_original_response.assert_awaited_once()

    async def test_recovery_network_calls_are_bounded(self):
        target = interaction()
        async def stall(**kwargs):
            await asyncio.Event().wait()
        target.edit_original_response.side_effect = stall
        await asyncio.wait_for(recover_response(target, "Retry", interaction=True), 0.3)
        target.delete_original_response.assert_awaited_once()

    async def test_typing_stops_on_success_error_timeout_and_cancel(self):
        for terminal in ("success", "error", "timeout", "cancel"):
            with self.subTest(terminal=terminal):
                state = {"typing": False}
                entered = asyncio.Event()
                @asynccontextmanager
                async def typing():
                    state["typing"] = True
                    entered.set()
                    try:
                        yield
                    finally:
                        state["typing"] = False
                async def send(**kwargs):
                    self.assertFalse(state["typing"])
                message = SimpleNamespace(channel=SimpleNamespace(typing=typing, send=AsyncMock(side_effect=send)))
                @bounded_message
                async def command(target):
                    async with typing_scope(target.channel):
                        if terminal == "error":
                            raise ValueError("Private error")
                        if terminal in ("timeout", "cancel"):
                            await asyncio.Event().wait()
                    await target.channel.send(content="Done")
                    mark_delivery()
                with self.assertLogs("discord-ai-agent.responses", level="INFO") as capture:
                    task = asyncio.create_task(command(message))
                    await entered.wait()
                    if terminal == "cancel":
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                    else:
                        await task
                self.assertFalse(state["typing"])
                self.assertIn("typing_finished", str(capture.output))
                self.assertIn("response_finished", str(capture.output))

    async def test_bot_item_wiki_failure_resolves_defer(self):
        import bot
        target = interaction()
        with patch.object(bot, "_capital_rift_note", AsyncMock(side_effect=RuntimeError("secret"))):
            await bot.item_lookup.callback(target, name="Computer")
        target.edit_original_response.assert_awaited_once()

    async def test_card_delivery_failure_recovers_without_leaving_thinking(self):
        import bot
        target = interaction()
        result = agent.AgentResult()
        result.text = "hello"
        with patch.object(bot, "run_agent", AsyncMock(return_value=result)), patch.object(bot, "_send_agent_result", AsyncMock(side_effect=RuntimeError("send failed"))):
            await bot.ask.callback(target, question="hello")
        target.edit_original_response.assert_awaited_once()

    async def test_outer_deadline_bounds_wiki_count(self):
        import bot
        target = interaction()
        cancelled = asyncio.Event()
        async def stalled():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        with patch.object(bot, "_deterministic_wiki_count_result", side_effect=stalled):
            await bot.ask.callback(target, question="How many items in Capital Rift?")
        self.assertTrue(cancelled.is_set())
        target.edit_original_response.assert_awaited_once()


class ToolAndLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_tool_name_cannot_inject_sensitive_logs(self):
        with self.assertLogs(agent.log, level="INFO") as capture:
            output, status = await agent._invoke_tool("secret user prompt", {}, turn_id="a" * 12, round_number=1, timeout=1)
        self.assertEqual(status, "error")
        self.assertNotIn("secret user prompt", str(capture.output))
        records = [json.loads(r.getMessage()) for r in capture.records]
        self.assertEqual(records[0]["call_id"], records[1]["call_id"])
        self.assertEqual(records[1]["tool"], "unknown")

    async def test_repeated_tool_calls_have_distinct_ids(self):
        with patch.dict(agent.TOOL_IMPLS, {"capital_rift_wiki": AsyncMock(return_value="{}")}), self.assertLogs(agent.log, level="INFO") as capture:
            for _ in range(2):
                await agent._invoke_tool("capital_rift_wiki", {}, turn_id="a" * 12, round_number=2, timeout=1)
        records = [json.loads(r.getMessage()) for r in capture.records]
        self.assertEqual(len({r["call_id"] for r in records}), 2)
        self.assertTrue(all(r["round"] == 2 and r["elapsed_ms"] >= 0 for r in records))

    async def test_model_failure_always_finishes_round_and_keeps_trace_id(self):
        trace = new_trace("ask")
        token = current_trace.set(trace)
        try:
            client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("secret")))))
            with patch.object(agent, "_client", client), patch.dict(agent.TOOL_IMPLS, {"capital_rift_wiki": AsyncMock(return_value="{}")}), self.assertLogs(agent.log, level="INFO") as capture:
                result = await agent.run_agent([], "private message")
            records = [json.loads(r.getMessage()) for r in capture.records]
            self.assertEqual(result.turn_id, trace.turn_id)
            self.assertEqual({r["turn_id"] for r in records}, {trace.turn_id})
            self.assertTrue(any(r["event"] == "round_finished" and r["status"] == "error" for r in records))
            self.assertNotIn("secret", str(capture.output))
        finally:
            current_trace.reset(token)

    async def test_search_request_cancels_without_a_lingering_thread(self):
        stopped = asyncio.Event()
        async def stalled(**kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        with patch.object(web_search, "_get_client", return_value=SimpleNamespace(search=AsyncMock(side_effect=stalled))):
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(web_search.web_search("query"), 0.02)
        self.assertTrue(stopped.is_set())

    async def test_packaging_offloads_and_contains_paths(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(codegen, "OUTPUT_ROOT", tmp):
            archive = await codegen.package_files("demo", [{"path": "src/main.py", "content": "print('hello')"}])
            self.assertTrue(Path(archive).is_file())
            for path in ("../escape.py", "C:/escape.py", "/escape.py"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    await codegen.package_files("bad", [{"path": path, "content": "bad"}])
            self.assertEqual(len(list(Path(tmp).glob("*.zip"))), 1)

    async def test_cancelled_packaging_removes_late_archive(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(codegen, "OUTPUT_ROOT", tmp):
            loop = asyncio.get_running_loop()
            started, cleaned = asyncio.Event(), asyncio.Event()
            release = threading.Event()
            actual = codegen._package
            def delayed(name, files, cancel):
                loop.call_soon_threadsafe(started.set)
                release.wait(1)
                try:
                    return actual(name, files, cancel)
                finally:
                    loop.call_soon_threadsafe(cleaned.set)
            with patch.object(codegen, "_package", side_effect=delayed):
                task = asyncio.create_task(codegen.package_files("demo", [{"path": "a", "content": "x"}]))
                await started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                release.set()
                await asyncio.wait_for(cleaned.wait(), 1)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    async def test_diagnostics_are_correlated_allowlisted_and_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log"
            path.write_text("\n".join([
                "A private prompt and a traceback",
                json.dumps({"event": "turn_error", "turn_id": "a" * 12, "status": "error", "prompt": "private prompt", "model": "secret-value"}),
                json.dumps({"event": "turn_finished", "turn_id": "b" * 12, "status": "completed"}),
            ]), encoding="utf-8")
            with patch.dict("os.environ", {"STABILITY_API_KEY": "secret-value"}):
                text = diagnostic_excerpt(path, "a" * 12)
            self.assertNotIn("private prompt", text)
            self.assertNotIn("secret-value", text)
            self.assertNotIn("b" * 12, text)
            self.assertIn("[REDACTED]", text)


class RetentionTests(unittest.TestCase):
    def test_log_rotation_has_bounded_backup_count(self):
        root = logging.getLogger()
        old_handlers, old_level = root.handlers[:], root.level
        # basicConfig(force=True) closes old handlers; keep them detached during the test.
        root.handlers = []
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"BOT_LOG_MAX_BYTES": "65536", "BOT_LOG_BACKUP_COUNT": "2"}):
                configure_logging(tmp)
                handler = next(h for h in root.handlers if hasattr(h, "maxBytes"))
                for _ in range(7):
                    handler.emit(logging.LogRecord("test", logging.INFO, "", 1, "x" * 40000, (), None))
                files = list(Path(tmp).glob("local-bot.log*"))
                self.assertLessEqual(len(files), 3)
                self.assertTrue(all(f.stat().st_size < 65536 for f in files))
                for h in root.handlers:
                    h.close()
        finally:
            root.handlers = old_handlers
            root.setLevel(old_level)


class CardFoundationTests(unittest.IsolatedAsyncioTestCase):
    async def test_states_have_text_labels_as_well_as_color(self):
        for state, label in [("success", "Success"), ("warning", "Warning"), ("error", "Error"), ("empty", "No results"), ("loading", "Working")]:
            view = build_card("Status", "Details", state=state)
            self.assertIn(label, view.to_components()[0]["components"][0]["content"])
        with self.assertRaises(CardError):
            build_card("Bad", "x" * 4100)
        view = build_response_views("Done", "Saved", state="success")[0]
        self.assertEqual(view.to_components()[0]["accent_color"], 0x2ECC71)

    async def test_wiki_link_near_boundary_is_not_cut(self):
        link = "[Computer](https://wiki.capitalrift.com/items/computer/)"
        text = "x " * 1480 + link + " trailing " * 20
        pages = paginate_text(text)
        self.assertEqual("".join(pages), text)
        self.assertEqual(sum(link in page for page in pages), 1)
        self.assertTrue(all(len(page) <= 3000 for page in pages))

    async def test_long_fenced_code_is_balanced_and_preserved(self):
        body = "print('hello')\n" * 500
        pages = paginate_text("```python\n" + body + "```")
        self.assertGreater(len(pages), 1)
        recovered = ""
        for page in pages:
            self.assertTrue(page.startswith("```python\n") and page.endswith("\n```"))
            self.assertLessEqual(len(page), 3000)
            recovered += page[len("```python\n"):-4]
        self.assertEqual(recovered, body)

    async def test_actions_require_accessible_labels_and_fit(self):
        view = build_card("Plan", "Details")
        add_actions(view, discord.ui.Button(label="Next"))
        self.assertLessEqual(view.total_children_count, 40)
        with self.assertRaises(CardError):
            add_actions(view, discord.ui.Button(emoji="➡️"))
