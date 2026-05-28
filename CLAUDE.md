# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
# Activate the virtual environment first
source .venv/bin/activate

# Run the Discord bot
python main.py
```

## Environment Configuration

Two env files are required at the project root:

**`.env`** — core settings:
- `DISCORD_TOKEN` — Discord bot token
- `OPENAI_API_KEY` — OpenAI API key
- `MODEL_CHAT` — OpenAI model (e.g. `gpt-5.4`)
- `PERSONALITY` — Active personality descriptor (short string injected into `BASE_SYSTEM_PROMPT`)
- `CHANNEL_IDS` — Comma-separated Discord channel IDs the bot listens to
- `HISTORYLENGTH` — Number of recent messages to fetch directly from Discord (default: 30)
- `RAG_MESSAGE_CONTEXT` — Number of semantically relevant past messages to retrieve from ChromaDB per response (default: 50)
- `MAX_TOKENS` — Max completion tokens for responses
- `MINECRAFT_VANILLA_DIR` — Path to vanilla server directory
- `MINECRAFT_VANILLA_RCON_HOST` — RCON host (default: localhost)
- `MINECRAFT_VANILLA_RCON_PORT` — RCON port (default: 25575)
- `MINECRAFT_VANILLA_RCON_PASSWORD` — RCON password
- `MINECRAFT_MODDED_DIR` — Path to modded server directory
- `MINECRAFT_MODDED_RCON_HOST` — RCON host (default: localhost)
- `MINECRAFT_MODDED_RCON_PORT` — RCON port (default: 25575)
- `MINECRAFT_MODDED_RCON_PASSWORD` — RCON password
- `GOOGLE_API_KEY` — Google Custom Search API key
- `GOOGLE_CSE_ID` — Google Custom Search Engine ID
- `VALHEIM_SERVER_NAME` — Valheim server display name
- `VALHEIM_WORLD_NAME` — Valheim world name
- `VALHEIM_PASSWORD` — Valheim server password
- `VALHEIM_PORT` — Valheim game port (default: 2456)
- `VALHEIM_STEAM_DIR` — Path to Steam directory (Windows)
- `ENSHROUDED_EXE` — Full path to enshrouded_server.exe (Windows)

**`personalities.env`** — short personality descriptors, one per line in the format `PERSONALITY=<descriptor>`. Each descriptor is injected into `BASE_SYSTEM_PROMPT` at the `{personality}` slot. Managed at runtime via `PersonalityManager`.

## Personality System

`BASE_SYSTEM_PROMPT` in `AIfunc/responses.py` is the shared system prompt used for all responses. It establishes:
- Discord platform context (concise, conversational)
- Code block formatting rules
- History handling (focus on recent message, use history as context)
- Stay-in-character directive

`bot.chatgpt_behaviour` holds the active short personality descriptor (e.g. `"a sarcastic assistant named Soupy Dafoe obsessed with soup"`). It is injected into `BASE_SYSTEM_PROMPT` at call time in `generate_gpt_response` and `analyze_image`. Personality descriptors should be short — the base prompt handles all boilerplate rules.

## RAG Memory System

Per-channel persistent memory backed by ChromaDB (`data/chroma/`). Every message the bot processes in an allowed channel is stored. Before each response, a semantic search retrieves relevant past messages and document chunks, which are injected into the system prompt as `RELEVANT CONTEXT FROM MEMORY`.

**Two document types in each collection:**
- `message` — a stored Discord message (role + content)
- `document` — a chunk from an uploaded file or `!learn` text

**Chunk size:** 3000 chars, 300-char overlap. Most small-to-medium files fit in one chunk.

**Context per response:**
- `HISTORYLENGTH` messages via `fetch_message_history` (direct Discord API)
- `RAG_MESSAGE_CONTEXT` semantically relevant messages from ChromaDB
- 5 relevant document chunks from ChromaDB

**Supported file types:** `.txt .py .md .js .ts .jsx .tsx .json .csv .yaml .yml .html .css .sh .toml .ini .cfg .pdf`

## Architecture Overview

`main.py` is the entry point (~30 lines). It initialises a `bridge.Bot`, sets shared state on the bot object, loads all Cogs via `bot.load_extension()`, and calls `bot.run()`. All commands and event handlers live in `cogs/`.

### Cog Layout

- **`cogs/chat.py`** — `ChatCog`: `on_message` (GPT chat handler + RAG storage/retrieval), `on_reaction_add`, `on_ready`, `on_command_error`. Contains `_should_respond()` logic: always responds to direct @mentions, responds in `CHANNEL_IDS` channels unless message is directed at a specific human. Supported file attachments are stored in RAG via `async_store_document`; the bot's response is stored via `async_store_message`.
- **`cogs/images.py`** — `ImagesCog`: `generate`, `transform`, `image` commands. `transform` has a separate `@commands.command()` for prefix (reads `ctx.message.attachments`) and a `@discord.slash_command()` for slash (takes explicit `attachment` option).
- **`cogs/personality.py`** — `PersonalityCog`: `!new`, `!change`, `!list` prefix commands and `/personality` slash command group (new/change/list/remove).
- **`cogs/games.py`** — `GamesCog`: `game` (Tic-Tac-Toe) and `snake` commands.
- **`cogs/servers.py`** — `ServersCog`: `minecraft` bridge command; Valheim prefix commands + `/valheim start|stop|status` slash group; Enshrouded prefix commands + `/enshrouded start|stop` slash group.
- **`cogs/fun.py`** — `FunCog`: `prompt` and `sandwich` bridge commands; `simulate` has a separate prefix command (flexible `*args`) and slash command (explicit `topic`, `p1`, `p2` params).
- **`cogs/rag.py`** — `RAGCog`: `learn` (prefix + slash, supports file attachment), `memory` and `cleardocs` (bridge commands), `clearall` (prefix only, requires Manage Messages).

### Slash vs Prefix

Most commands use `@bridge.bridge_command()` which creates both a `!prefix` and `/slash` command automatically. Exceptions where bridge doesn't work cleanly:
- **`transform`**: prefix uses `ctx.message.attachments`; slash uses a `discord.Attachment` option
- **`simulate`**: prefix uses `*args` (flexible `[p1] [p2] <topic>`); slash has explicit typed params
- **`learn`**: prefix reads `ctx.message.attachments`; slash has an explicit `discord.Attachment` option

### Support Modules

- **`AIfunc/responses.py`** — `BASE_SYSTEM_PROMPT` constant; `generate_gpt_response()` (accepts optional `rag_context: list[str]`), `analyze_image()`, `generate_image()`, `transform_image()`.
- **`AIfunc/simulate.py`** — `ConversationSimulator`.
- **`chatbotfunc/utils.py`** — `fetch_message_history()`, `async_chat_completion()`, `split_message()`, `format_error_message()`, `encode_discord_image()`.
- **`chatbotfunc/personalitymanager.py`** — `PersonalityManager`: reads/writes/manages personality descriptors from `personalities.env`.
- **`ragfunc/memory.py`** — `ChannelMemory` class (ChromaDB wrapper); `store_message()`, `store_document()`, `retrieve()`, `retrieve_documents_expanded()`, `clear_documents()`, `clear_all()`; async helpers: `async_store_message`, `async_store_document`, `async_retrieve`, `async_count`, `async_clear_documents`, `async_clear_all`.
- **`gamefunc/minecraft.py`** — Thread-safe async RCON using `socket.settimeout()` (not the `mcrcon` library, which uses `signal.alarm()` and crashes outside the main thread).
- **`gamefunc/minecraft_panel.py`** — `MinecraftPanel` Discord UI with live status embed and button enable/disable rules.
- **`gamefunc/valheim.py`** — `ValheimServer`, `EnshroudedServer` (Windows-only).
- **`funfunc/`** — Image search, GPT search prompt, sandwich generator.

### Shared State

All mutable state lives on the bot object, accessible from any Cog via `self.bot`:

- `bot.chatgpt_behaviour` — Active personality descriptor string; changed by `!change` / `/personality change`
- `bot.active_games` — `dict[channel_id, bool]` prevents message handling during in-channel games
- `bot.last_generated_image_bytes` — Raw PNG bytes of the last `!generate` result; used by `!transform last`
- `bot.personality_manager` — `PersonalityManager` instance

### Message Flow

`on_message` in `ChatCog`:
1. Returns early if message is from the bot itself
2. Returns early for `!`-prefixed messages (bot routes commands automatically via `bridge.Bot`)
3. Skips channels with active games
4. Processes image attachments via `analyze_image()` if present in an allowed channel
5. If a supported file is attached, downloads it, stores in ChromaDB via `async_store_document`, breaks
6. Calls `_should_respond()`: True if bot is @mentioned (any channel) OR if channel is in `CHANNEL_IDS` and no human @mentions are present
7. Stores user message in ChromaDB via `async_store_message`
8. Retrieves RAG context: top-5 document chunks + top-`RAG_MESSAGE_CONTEXT` message chunks
9. Fetches direct Discord history via `fetch_message_history`, appends user message
10. Calls `generate_gpt_response()` with RAG context injected into system prompt
11. Stores bot response in ChromaDB, sends via `split_message()`

### Bot Commands Reference

| Prefix | Slash | Description |
|---|---|---|
| `!generate <prompt>` | `/generate` | Generate an image via gpt-image-1 |
| `!transform <instructions>` | `/transform` | Transform an image |
| `!transform last <instructions>` | `/transform use_last:True` | Transform the last generated image |
| `!image <query>` | `/image` | Search and display an image with AI description |

| `!change [n]` | — | Switch to personality #n or random |
| `!new <descriptor>` | — | Add a new personality descriptor |
| `!list` | — | List available personalities |
| — | `/personality change\|new\|list\|remove` | Personality slash commands |
| `!simulate [p1] [p2] <topic>` | `/simulate` | Simulate conversation between two personalities |
| `!game X\|O` | `/game` | Play Tic-Tac-Toe |
| `!snake` | `/snake` | Play Snake |
| `!minecraft` | `/minecraft` | Open the Minecraft server management panel |
| `!start_valheim` / `!stop_valheim` | `/valheim start\|stop\|status` | Manage Valheim server |
| `!start_enshrouded` / `!stop_enshrouded` | `/enshrouded start\|stop` | Manage Enshrouded server |
| `!prompt <topic>` | `/prompt` | Generate a Google search URL for a topic |
| `!sandwich` | `/sandwich` | Generate a random sandwich |
| `!learn [text]` | `/learn` | Store text or file in RAG memory |
| `!memory` | `/memory` | Show memory stats for this channel |
| `!cleardocs` | `/cleardocs` | Clear stored documents (keeps message history) |
| `!clearall` | — | Wipe all memory for this channel (Manage Messages required) |
