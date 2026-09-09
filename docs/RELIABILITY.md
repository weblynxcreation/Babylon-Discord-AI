# Response reliability and operations

This covers the canonical Discord gateway bot and issues #17, #18, and #16.
The legacy HTTP interactions endpoint shares the agent deadline but does not use
the gateway response lifecycle; it is not the local test bot's entry point.

## Budgets

| Setting | Default | Covers |
| --- | ---: | --- |
| NVIDIA_REQUEST_TIMEOUT_SECONDS | 45 s | Each model request, including the final answer |
| AGENT_TOOL_TIMEOUT_SECONDS | 45 s | Each tool call |
| AGENT_TURN_TIMEOUT_SECONDS | 120 s | Wiki preflight, model calls, and tools together |
| DISCORD_RESPONSE_TIMEOUT_SECONDS | 150 s | The complete deferred command or conversation handler, including history, wiki-only routes, rendering, and delivery |
| DISCORD_RECOVERY_TIMEOUT_SECONDS | 5 s | Each recovery API call or delivery verification |

All budgets must be positive and finite. Request retries are disabled in the
model client. Tool failures become explicit evidence for the model; a subsequent
round can recover without inventing a result. Model/overall timeouts end the turn
with a readable fallback and request reference.

The outer response guard cancels the handler on deadline. For an unresolved slash
response, it edits the original deferred message with a fallback. If that fails,
it attempts to delete the loading response. Recovery is bounded to two API calls.
If Discord is unreachable, cleanup failure is logged; no code can clear a remote
indicator without a successful Discord request.

Typing refresh runs inside a finally-protected context and ends on success,
error, timeout, or cancellation. Discord may briefly retain its last typing pulse.
External cancellation is acknowledged when possible and then re-raised.
Successful direct-send paths are checked for a forgotten loading response.
All top-level commands that defer have the shared response guard. The diagnostic
button has its own short deadline and cancellation cleanup.

Tavily search uses cancellable async HTTP. ZIP work and GIF encoding run off the
event loop. ZIP jobs are capped at 64 files / 5 MiB and remove incomplete or late
archives after cancellation. CPU/file worker threads cannot be forcibly killed;
bounded local work can finish in the background but cannot post a late response.

## Searchable logs

Every guarded response has a 12-character turn_id shared with its agent/tool
events. Each tool invocation also has its own call_id, including repeated calls
to the same tool. Records contain event, elapsed_ms, round, tool, status, and
safe operational fields. They never contain prompts, tool arguments/results,
message text, provider exception bodies, or credentials. Unknown tool names are
logged as unknown.

Terminal events include tool_finished, model_finished, round_finished,
turn_finished, typing_finished, and response_finished. Search by the Ref shown in
a timeout response, or by event/status. Watch response_failed, unresolved_defer,
response_verification_failed, recovery_failed, and missing terminal events.
No recurring monitoring job is installed by this change.

The local launcher writes logs/local-bot.log with size rotation:
BOT_LOG_MAX_BYTES defaults to 2 MiB; BOT_LOG_BACKUP_COUNT defaults to 3.
That retains the active file and three backups (about 8 MiB total under normal
event sizes). Retention is size-based, not a promise of a specific number of days.
SDK HTTP debug logging is disabled.

The Send logs button exports only structured, allowlisted events for that request
from the recent log tail. Known environment secrets are redacted. It requires a
configured mod_log_channel_id; it never falls back to a public channel or exports
arbitrary historical tracebacks. Diagnostic files are at most 18,000 characters.

## Verification

Run the offline unittest suite. tests/test_issue_reliability.py covers stalled
wiki/model work, cancellation, recovery on the next request, failed Discord
delivery, missing follow-ups, typing cleanup, correlated IDs, safe diagnostic
exports, rotation, and cancellation of search/packaging.

For a live check in the development guild, temporarily lower the turn deadline,
run /ask, and confirm a terminal response followed by a successful next request.
Restore the deadline afterward. Network/provider interactions in automated tests
are mocked; startup and guild command sync are verified separately.
