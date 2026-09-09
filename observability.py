"""Privacy-safe request tracing and bounded local log retention."""
from contextvars import ContextVar
from dataclasses import dataclass
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
from time import monotonic
from uuid import uuid4

@dataclass
class ResponseTrace:
    turn_id: str
    started: float
    source: str
    status: str = "completed"
    delivered: bool = False

current_trace = ContextVar("response_trace", default=None)
log = logging.getLogger("discord-ai-agent.responses")
FIELDS = {"round", "tool", "tools", "call_id", "status", "error_type", "model",
          "final", "timeout_seconds", "source", "phase", "recovered"}


def event(logger, name, turn_id, started, **fields):
    safe = {key: value for key, value in fields.items() if key in FIELDS}
    logger.info(json.dumps({
        "event": name, "turn_id": turn_id,
        "elapsed_ms": max(0, round((monotonic() - started) * 1000)), **safe,
    }, separators=(",", ":")))


def trace_event(name, **fields):
    trace = current_trace.get()
    if trace:
        event(log, name, trace.turn_id, trace.started, source=trace.source, **fields)


def mark_delivery():
    trace = current_trace.get()
    if trace and not trace.delivered:
        trace.delivered = True
        trace_event("response_delivered", status=trace.status)


def mark_status(status):
    trace = current_trace.get()
    if trace:
        trace.status = status


def new_trace(source):
    return ResponseTrace(uuid4().hex[:12], monotonic(), source)


def configure_logging(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    max_bytes = int(os.environ.get("BOT_LOG_MAX_BYTES", "2097152"))
    backups = int(os.environ.get("BOT_LOG_BACKUP_COUNT", "3"))
    if not 65536 <= max_bytes <= 20971520 or not 1 <= backups <= 10:
        raise ValueError("Log size must be 64 KiB–20 MiB, with 1–10 backups.")
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(directory / "local-bot.log", maxBytes=max_bytes,
                            backupCount=backups, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=handlers, force=True)
    # SDK request URLs can contain private query strings; never enable HTTP debug logs.
    for name in ("httpx", "httpcore", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)


def diagnostic_excerpt(path, turn_id=None):
    """Export only allowlisted structured events, never arbitrary log/traceback text."""
    records = []
    for candidate in (Path(str(path) + ".1"), Path(path)):
        if not candidate.exists():
            continue
        with candidate.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 65536))
            text = stream.read(65536).decode("utf-8", errors="replace")
        for line in text.splitlines():
            start = line.find("{")
            if start < 0:
                continue
            try:
                record = json.loads(line[start:])
            except ValueError:
                continue
            if not isinstance(record, dict) or not re.fullmatch(r"[a-f0-9]{12}", str(record.get("turn_id", ""))):
                continue
            if turn_id and record["turn_id"] != turn_id:
                continue
            safe = {key: value for key, value in record.items()
                    if key in FIELDS | {"event", "turn_id", "elapsed_ms"}}
            records.append(json.dumps(safe, separators=(",", ":")))
    # Keep whole event records at the tail.
    chosen, size = [], 0
    for line in reversed(records):
        if size + len(line) + 1 > 18000:
            break
        chosen.append(line)
        size += len(line) + 1
    result = "\n".join(reversed(chosen)) or "No structured diagnostic events were found for this request."
    for name, value in os.environ.items():
        if any(marker in name.upper() for marker in ("TOKEN", "KEY", "SECRET", "PASSWORD")) and len(value) >= 6:
            result = result.replace(value, "[REDACTED]")
    return result
