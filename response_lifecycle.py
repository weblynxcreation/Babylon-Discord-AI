"""Bound the whole Discord response, including wiki, history, and delivery paths."""
import asyncio
from contextlib import asynccontextmanager
from functools import wraps
import discord

from observability import current_trace, new_trace, trace_event, mark_delivery
from reliability import timeout_seconds


async def recover_response(target, text, *, interaction):
    """Resolve a defer first; if delivery fails, at least remove the loading response."""
    timeout = timeout_seconds("DISCORD_RECOVERY_TIMEOUT_SECONDS", 5)
    kwargs = {"content": text, "allowed_mentions": discord.AllowedMentions.none()}
    if not interaction:
        try:
            await asyncio.wait_for(target.channel.send(**kwargs), timeout)
            mark_delivery()
        except Exception as exc:
            trace_event("recovery_failed", error_type=type(exc).__name__)
        return
    try:
        if target.response.is_done():
            await asyncio.wait_for(target.edit_original_response(**kwargs, view=None, attachments=[]), timeout)
        else:
            await asyncio.wait_for(target.response.send_message(**kwargs, ephemeral=True), timeout)
        mark_delivery()
        return
    except Exception as exc:
        trace_event("recovery_edit_failed", error_type=type(exc).__name__)
    try:
        await asyncio.wait_for(target.delete_original_response(), timeout)
        trace_event("deferred_response_cleared")
    except Exception as exc:
        trace_event("recovery_failed", error_type=type(exc).__name__)


async def _run_bounded(callback, target, args, kwargs, *, interaction):
    trace = new_trace(callback.__name__)
    token = current_trace.set(trace)
    budget = timeout_seconds("DISCORD_RESPONSE_TIMEOUT_SECONDS", 150)
    trace_event("response_started", timeout_seconds=budget)
    try:
        await asyncio.wait_for(callback(target, *args, **kwargs), budget)
        # Shared senders record delivery. Check direct Discord send paths too.
        if interaction and not trace.delivered and hasattr(target, "original_response"):
            try:
                original = await asyncio.wait_for(target.original_response(), timeout_seconds("DISCORD_RECOVERY_TIMEOUT_SECONDS", 5))
                if original.flags.loading:
                    trace.status = "error"
                    trace_event("unresolved_defer", status="error")
                    await recover_response(target, f"The command finished without a response. Please try again. Ref: {trace.turn_id}", interaction=True)
                else:
                    mark_delivery()
            except Exception as exc:
                trace_event("response_verification_failed", error_type=type(exc).__name__)
    except asyncio.CancelledError:
        trace.status = "cancelled"
        trace_event("response_cancelled", status=trace.status)
        if not trace.delivered:
            await recover_response(target, f"This request was cancelled. Please try again. Ref: {trace.turn_id}", interaction=interaction)
        raise
    except Exception as exc:
        trace.status = "timeout" if isinstance(exc, asyncio.TimeoutError) else "error"
        trace_event("response_failed", status=trace.status, error_type=type(exc).__name__)
        text = "This request took too long, so I stopped it." if trace.status == "timeout" else "I couldn't complete this request."
        if not trace.delivered:
            await recover_response(target, f"{text} Please try again. Ref: {trace.turn_id}", interaction=interaction)
    finally:
        trace_event("response_finished", status=trace.status)
        current_trace.reset(token)


def bounded_command(callback):
    @wraps(callback)
    async def wrapped(interaction, *args, **kwargs):
        return await _run_bounded(callback, interaction, args, kwargs, interaction=True)
    return wrapped


def bounded_message(callback):
    @wraps(callback)
    async def wrapped(message, *args, **kwargs):
        return await _run_bounded(callback, message, args, kwargs, interaction=False)
    return wrapped


@asynccontextmanager
async def typing_scope(channel):
    trace_event("typing_started")
    try:
        async with channel.typing():
            yield
    finally:
        # Discord expires its last typing pulse; the refresh task is stopped here.
        trace_event("typing_finished")
