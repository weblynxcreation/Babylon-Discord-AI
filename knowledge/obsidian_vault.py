"""Read-only Obsidian Markdown indexing backed by a local SQLite FTS index."""
import asyncio
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

EXCLUDED_DIRECTORIES = {".obsidian", ".trash", ".git", ".svn", "node_modules"}
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'’-]*")
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


class VaultError(RuntimeError):
    pass


@dataclass(frozen=True)
class VaultSearchResult:
    path: str
    title: str
    excerpt: str
    score: float


class ObsidianVaultIndex:
    """Indexes Markdown without ever writing inside the Obsidian vault."""

    def __init__(
        self,
        vault_path: str,
        index_path: str,
        *,
        refresh_seconds: float = 30,
        max_note_bytes: int = 2 * 1024 * 1024,
    ):
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.index_path = Path(index_path).expanduser().resolve()
        self.refresh_seconds = max(0.0, refresh_seconds)
        self.max_note_bytes = max_note_bytes
        self._last_sync = 0.0
        self._lock = asyncio.Lock()

    def _validate_vault(self) -> None:
        if not self.vault_path.exists():
            raise VaultError(f"Obsidian vault does not exist: {self.vault_path}")
        if not self.vault_path.is_dir():
            raise VaultError(f"Obsidian vault path is not a directory: {self.vault_path}")

    def _connect(self) -> sqlite3.Connection:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.index_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS note_metadata (
                path TEXT PRIMARY KEY,
                mtime_ns INTEGER NOT NULL,
                size INTEGER NOT NULL,
                title TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                path UNINDEXED,
                title,
                content,
                tokenize='unicode61'
            )
            """
        )
        return conn

    def _markdown_files(self):
        for path in self.vault_path.rglob("*.md"):
            relative = path.relative_to(self.vault_path)
            if any(part in EXCLUDED_DIRECTORIES or part.startswith(".") for part in relative.parts[:-1]):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            yield path, relative.as_posix()

    @staticmethod
    def _title(relative_path: str, content: str) -> str:
        match = HEADING_RE.search(content)
        if match:
            return match.group(1).strip()[:200]
        return Path(relative_path).stem.replace("_", " ").strip()[:200]

    def _sync_blocking(self, force: bool) -> dict:
        self._validate_vault()
        conn = self._connect()
        indexed = 0
        removed = 0
        skipped = 0
        try:
            existing = {
                row[0]: (row[1], row[2])
                for row in conn.execute(
                    "SELECT path, mtime_ns, size FROM note_metadata"
                ).fetchall()
            }
            discovered = set()

            for path, relative in self._markdown_files():
                discovered.add(relative)
                stat = path.stat()
                if stat.st_size > self.max_note_bytes:
                    skipped += 1
                    continue
                if not force and existing.get(relative) == (stat.st_mtime_ns, stat.st_size):
                    continue

                try:
                    content = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    skipped += 1
                    continue

                title = self._title(relative, content)
                conn.execute("DELETE FROM notes_fts WHERE path = ?", (relative,))
                conn.execute(
                    "INSERT INTO notes_fts(path, title, content) VALUES (?, ?, ?)",
                    (relative, title, content),
                )
                conn.execute(
                    """
                    INSERT INTO note_metadata(path, mtime_ns, size, title)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        mtime_ns=excluded.mtime_ns,
                        size=excluded.size,
                        title=excluded.title
                    """,
                    (relative, stat.st_mtime_ns, stat.st_size, title),
                )
                indexed += 1

            for relative in set(existing) - discovered:
                conn.execute("DELETE FROM notes_fts WHERE path = ?", (relative,))
                conn.execute("DELETE FROM note_metadata WHERE path = ?", (relative,))
                removed += 1

            conn.commit()
            total = conn.execute("SELECT COUNT(*) FROM note_metadata").fetchone()[0]
            return {
                "totalNotes": total,
                "updatedNotes": indexed,
                "removedNotes": removed,
                "skippedNotes": skipped,
            }
        finally:
            conn.close()

    async def sync(self, *, force: bool = False) -> dict:
        async with self._lock:
            now = time.monotonic()
            if not force and now - self._last_sync < self.refresh_seconds:
                return await asyncio.to_thread(self._status_blocking)
            result = await asyncio.to_thread(self._sync_blocking, force)
            self._last_sync = time.monotonic()
            return result

    def _status_blocking(self) -> dict:
        self._validate_vault()
        conn = self._connect()
        try:
            total = conn.execute("SELECT COUNT(*) FROM note_metadata").fetchone()[0]
            return {"totalNotes": total}
        finally:
            conn.close()

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = TOKEN_RE.findall(query)[:12]
        if not terms:
            raise VaultError("Search query must contain letters or numbers.")
        return " OR ".join(f'"{term.replace(chr(34), "")}"*' for term in terms)

    def _search_blocking(self, query: str, limit: int) -> list[VaultSearchResult]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT path, title,
                       snippet(notes_fts, 2, '', '', ' … ', 36),
                       bm25(notes_fts)
                FROM notes_fts
                WHERE notes_fts MATCH ?
                ORDER BY bm25(notes_fts)
                LIMIT ?
                """,
                (self._fts_query(query), limit),
            ).fetchall()
            return [
                VaultSearchResult(
                    path=path,
                    title=title,
                    excerpt=" ".join(excerpt.split()),
                    score=float(score),
                )
                for path, title, excerpt, score in rows
            ]
        finally:
            conn.close()

    async def search(self, query: str, *, limit: int = 5) -> list[VaultSearchResult]:
        await self.sync()
        safe_limit = max(1, min(int(limit), 10))
        return await asyncio.to_thread(self._search_blocking, query, safe_limit)

    def _resolve_note(self, relative_path: str) -> Path:
        unresolved = self.vault_path / relative_path
        if unresolved.is_symlink():
            raise VaultError("Symbolic-link notes are not permitted.")
        candidate = unresolved.resolve()
        try:
            candidate.relative_to(self.vault_path)
        except ValueError as exc:
            raise VaultError("Requested note is outside the configured vault.") from exc
        if candidate.suffix.casefold() != ".md" or not candidate.is_file():
            raise VaultError("Requested Markdown note was not found.")
        return candidate

    async def read_note(self, relative_path: str, *, max_characters: int = 12000) -> dict:
        await self.sync()
        path = self._resolve_note(relative_path)

        def read():
            if path.stat().st_size > self.max_note_bytes:
                raise VaultError("Requested note is larger than the configured safety limit.")
            content = path.read_text(encoding="utf-8")
            truncated = len(content) > max_characters
            return {
                "path": path.relative_to(self.vault_path).as_posix(),
                "title": self._title(relative_path, content),
                "content": content[:max_characters],
                "truncated": truncated,
            }

        return await asyncio.to_thread(read)

    async def status(self) -> dict:
        sync_result = await self.sync()
        return {
            **sync_result,
            "vaultPath": str(self.vault_path),
            "indexPath": str(self.index_path),
            "readOnlyVault": True,
        }
