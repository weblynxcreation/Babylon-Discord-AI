# Capital Rift Obsidian Vault Setup

The bot can index a local Obsidian vault and use it as read-only reference
material for Capital Rift questions and production calculations.

## Host requirement

The vault must be available as a normal folder on the same computer that runs
the Discord bot. A cloud-only shortcut is not enough; files must be downloaded
locally. If the vault is synchronized by OneDrive, Dropbox, Git, or Obsidian
Sync, allow synchronization to finish before testing the bot.

## Configure the path

In the bot's local .env file, add:

    CAPITAL_RIFT_VAULT_PATH=C:/Users/OWNER/Documents/Capital Rift Wiki
    CAPITAL_RIFT_VAULT_REFRESH_SECONDS=30
    CAPITAL_RIFT_MAX_NOTE_BYTES=2097152

Forward slashes are recommended in Windows paths. Do not add quotation marks
unless the environment parser requires them.

The optional CAPITAL_RIFT_INDEX_PATH setting can place the SQLite search index
somewhere else. When omitted, the bot uses:

    discord-ai-agent/data/capital_rift_wiki.db

The data directory is already excluded from Git.

## Read-only guarantees

The bot:

- reads only Markdown files ending in .md;
- never creates, edits, renames, or deletes vault files;
- skips .obsidian, .trash, .git, other hidden directories, node_modules, and
  symbolic-link notes;
- rejects note paths that resolve outside the configured vault;
- limits note size and returned content;
- writes its searchable SQLite index only in the bot's own data directory.

The local index contains a searchable copy of note text. Delete the index file
to erase that copy; it is rebuilt automatically from the vault.

## First test

1. Restart the bot after editing .env.
2. Run /wiki-status as a configured bot administrator.
3. Confirm it reports the expected number of indexed notes.
4. Mention the bot and ask: "According to the Capital Rift wiki, how do I make
   an iron plate?"
5. Ask for a production target such as: "Using the wiki recipe, calculate a
   line producing 120 iron plates per minute."

Answers should name the supporting note. If required recipe values are absent
or ambiguous, the bot should say what is missing instead of inventing numbers.

## Updating the wiki

The index checks for changed, added, and removed Markdown notes on demand. The
default refresh window is 30 seconds, so ordinary Obsidian edits require no bot
restart.

## Current limitations

- Images, PDFs, canvases, and other attachments are not indexed yet.
- Wiki links are searchable as Markdown text but are not yet traversed as a
  knowledge graph.
- The deterministic calculator handles one verified recipe step at a time.
  Fully optimized multi-stage factory planning will require a structured recipe
  catalog derived from and validated against the wiki.
