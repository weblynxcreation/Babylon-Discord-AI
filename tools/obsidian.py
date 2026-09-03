"""
Obsidian vault integration: search and read notes from a local Obsidian vault.
Uses full-text search (FTS) to find relevant notes based on user queries.
"""
import os
import asyncio
from pathlib import Path
import sqlite3
import json

VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH", "")

# Tool schema for obsidian_search
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "obsidian_search",
        "description": "Search the Obsidian vault for notes matching a query. Returns a list of matching note files and brief excerpts.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query (e.g., 'foundries iron bars', 'copper production'). Searches note content and filenames."
                }
            },
            "required": ["query"]
        }
    }
}

TOOL_SCHEMA_READ = {
    "type": "function",
    "function": {
        "name": "obsidian_read",
        "description": "Read the full content of a specific note from the Obsidian vault.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "The note filename (with or without .md extension), relative to vault root (e.g., 'Wiki/Production' or 'Production.md')"
                }
            },
            "required": ["filename"]
        }
    }
}


def _normalize_path(filename: str) -> Path:
    """Normalize a filename to a Path object relative to vault root."""
    # Remove .md if present
    if filename.endswith(".md"):
        filename = filename[:-3]
    
    # Build path and ensure it's within vault
    vault = Path(VAULT_PATH)
    note_path = (vault / filename).with_suffix(".md")
    
    # Security: ensure path is within vault
    try:
        note_path.relative_to(vault)
    except ValueError:
        raise ValueError(f"Path {filename} is outside vault")
    
    return note_path


def _get_all_markdown_files() -> list[Path]:
    """Get all markdown files in the vault."""
    vault = Path(VAULT_PATH)
    if not vault.exists():
        return []
    return list(vault.rglob("*.md"))


def _build_fts_index() -> str:
    """
    Build a temporary FTS index from vault content.
    Returns path to the temporary SQLite database.
    """
    import tempfile
    
    # Create temp DB for FTS
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db.close()
    
    conn = sqlite3.connect(temp_db.name)
    cursor = conn.cursor()
    
    # Create FTS5 virtual table
    cursor.execute("""
        CREATE VIRTUAL TABLE notes_fts USING fts5(
            filename,
            content,
            tokenize='porter'
        )
    """)
    
    # Index all markdown files
    for md_file in _get_all_markdown_files():
        try:
            with open(md_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            # Get relative path for display
            rel_path = md_file.relative_to(VAULT_PATH).as_posix()
            
            cursor.execute(
                "INSERT INTO notes_fts(filename, content) VALUES(?, ?)",
                (rel_path, content)
            )
        except Exception as e:
            print(f"Error indexing {md_file}: {e}")
    
    conn.commit()
    return temp_db.name, conn


async def obsidian_search(query: str) -> str:
    """
    Search the Obsidian vault for notes matching the query.
    Returns JSON with matching notes and excerpts.
    """
    if not VAULT_PATH:
        return json.dumps({"error": "OBSIDIAN_VAULT_PATH not configured"})
    
    vault = Path(VAULT_PATH)
    if not vault.exists():
        return json.dumps({"error": f"Vault path does not exist: {VAULT_PATH}"})
    
    try:
        # Build FTS index in a thread to avoid blocking
        db_path, conn = await asyncio.to_thread(_build_fts_index)
        
        try:
            cursor = conn.cursor()
            
            # FTS search - match any word in the query
            search_terms = " OR ".join(f'"{term}"' for term in query.split())
            cursor.execute(
                f"""
                SELECT filename, content, rank 
                FROM notes_fts 
                WHERE notes_fts MATCH ?
                ORDER BY rank
                LIMIT 10
                """,
                (search_terms,)
            )
            
            results = cursor.fetchall()
            
            if not results:
                return json.dumps({
                    "query": query,
                    "results": [],
                    "message": "No matching notes found"
                })
            
            # Format results with excerpts
            formatted_results = []
            for filename, content, rank in results:
                # Extract a relevant excerpt (first 300 chars or around query term)
                excerpt = content[:300]
                if len(content) > 300:
                    excerpt += "..."
                
                formatted_results.append({
                    "filename": filename,
                    "excerpt": excerpt
                })
            
            return json.dumps({
                "query": query,
                "results": formatted_results,
                "count": len(formatted_results)
            })
        
        finally:
            conn.close()
            os.unlink(db_path)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


async def obsidian_read(filename: str) -> str:
    """
    Read the full content of a specific note from the vault.
    Returns the raw markdown content.
    """
    if not VAULT_PATH:
        return "Error: OBSIDIAN_VAULT_PATH not configured"
    
    try:
        note_path = _normalize_path(filename)
        
        if not note_path.exists():
            return f"Error: Note '{filename}' not found in vault"
        
        with open(note_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        # Cap at ~6000 chars like web_scrape does, to not overflow context
        if len(content) > 6000:
            content = content[:6000] + "\n\n[... note truncated ...]"
        
        return content
    
    except Exception as e:
        return f"Error reading note: {e}"
