"""
Persistent conversation history, per channel and per DM, so the bot
remembers context across restarts instead of losing it every time the
process stops (which is what the original in-memory-only version did).

Uses stdlib sqlite3 — no extra dependency. sqlite3 calls are blocking, so
every function here runs its DB work through asyncio.to_thread to keep the
bot's event loop unblocked.

One database, one "messages" table, keyed by Discord channel ID — this
covers both guild text channels and DM channels transparently, since
Discord gives both a unique channel.id.
"""
import os
import sqlite3
import asyncio
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "chat_history.db")

_init_lock = asyncio.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            ts REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_channel_id ON messages(channel_id, id)")
    return conn


async def _ensure_init() -> None:
    global _initialized
    if _initialized:
        return
    async with _init_lock:
        if _initialized:
            return

        def _init():
            _connect().close()

        await asyncio.to_thread(_init)
        _initialized = True


async def append_message(channel_id: int, role: str, content: str, max_history: int = 40) -> None:
    """Stores one message and trims the channel's history to the most recent max_history rows."""
    await _ensure_init()

    def _write():
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO messages (channel_id, role, content, ts) VALUES (?, ?, ?, ?)",
                (channel_id, role, content, time.time()),
            )
            conn.execute(
                """
                DELETE FROM messages
                WHERE channel_id = ? AND id NOT IN (
                    SELECT id FROM messages WHERE channel_id = ? ORDER BY id DESC LIMIT ?
                )
                """,
                (channel_id, channel_id, max_history),
            )
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_write)


async def get_history(channel_id: int, limit: int = 40) -> list[dict]:
    """Returns this channel's recent history, oldest-first, as {"role", "content"} dicts."""
    await _ensure_init()

    def _read():
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
                (channel_id, limit),
            ).fetchall()
            return list(reversed(rows))
        finally:
            conn.close()

    rows = await asyncio.to_thread(_read)
    return [{"role": role, "content": content} for role, content in rows]


async def clear_history(channel_id: int) -> None:
    """Wipes stored history for one channel (e.g. via a /clearhistory command)."""
    await _ensure_init()

    def _clear():
        conn = _connect()
        try:
            conn.execute("DELETE FROM messages WHERE channel_id = ?", (channel_id,))
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_clear)
