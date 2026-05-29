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

A single **`.env`** file at the project root holds all configuration:

- `DISCORD_TOKEN` — Discord bot token
- `OPENAI_API_KEY` — OpenAI API key
- `MODEL_CHAT` — OpenAI model (e.g. `gpt-5.4`)
- `CHANNEL_IDS` — Comma-separated Discord channel IDs the bot listens to
- `HISTORYLENGTH` — Number of recent messages to fetch directly from Discord (default: 30)
- `RAG_MESSAGE_CONTEXT` — Number of semantically relevant past messages to retrieve from ChromaDB per response (default: 50)
- `MESSAGE_TTL_DAYS` — Days before a stored chat message is excluded from retrieval (default: 30). Documents never expire.
- `DISTANCE_THRESHOLD` — Cosine distance cutoff for RAG retrieval (default: 0.8). Results above this are dropped.
- `MAX_TOKENS` — Max completion tokens for responses
- `REACTION_RESPONSES` — `true` / `false` — enable or disable emoji reaction responses (default: `true`)
- `LOG_LEVEL` — Python logging level written to `data/bot.log` (default: `WARNING`). Set to `INFO` or `DEBUG` for more verbose file logging. Console always shows INFO+.
- `MINECRAFT_VANILLA_DIR` — Path to vanilla server directory
- `MINECRAFT_VANILLA_RCON_HOST` — RCON host (default: localhost)
- `MINECRAFT_VANILLA_RCON_PORT` — RCON port (default: 25575)
- `MINECRAFT_VANILLA_RCON_PASSWORD` — RCON password
- `MINECRAFT_MODDED_DIR` — Path to modded server directory
- `MINECRAFT_MODDED_RCON_HOST` — RCON host (default: localhost)
- `MINECRAFT_MODDED_RCON_PORT` — RCON port (default: 25575)
- `MINECRAFT_MODDED_RCON_PASSWORD` — RCON password
- `GOOGLE_API_KEY` — Google Custom Search API key (used by `!image` image search)
- `GOOGLE_CSE_ID` — Google Custom Search Engine ID (used by `!image` image search)
- `TAVILY_API_KEY` — Tavily API key for the AI web search tool (`google_search` tool in `chat.py`). Get one free at tavily.com.
- `VALHEIM_SERVER_NAME` — Valheim server display name
- `VALHEIM_WORLD_NAME` — Valheim world name
- `VALHEIM_PASSWORD` — Valheim server password
- `VALHEIM_PORT` — Valheim game port (default: 2456)
- `VALHEIM_STEAM_DIR` — Path to Steam directory (Windows)
- `ENSHROUDED_EXE` — Full path to enshrouded_server.exe (Windows)
- `PERSONALITY=<descriptor>` — One line per personality (repeated key). Each is a short character descriptor injected into `BASE_SYSTEM_PROMPT`. Managed at runtime via `PersonalityManager`.
- `ACTIVE_PERSONALITY=<descriptor>` — Written automatically by `PersonalityManager.set_active()` when a personality change is made. Read on startup to restore the last selected personality.

## Personality System

`BASE_SYSTEM_PROMPT` in `AIfunc/responses.py` is the shared system prompt used for all responses. It establishes:
- Discord platform context (concise, conversational, match conversation energy)
- No hollow filler openers ("Great question!", "Certainly!", etc.)
- Code block formatting rules
- RAG context handling: treat injected memory as natural background knowledge, do not announce it
- History handling (focus on recent message, use history as supporting context only)
- Stay-in-character directive — personality shapes voice/tone, not factual accuracy
- Uncertainty: admit "I'm not sure" in character rather than fabricating

`bot.chatgpt_behaviour` holds the active short personality descriptor (e.g. `"a sarcastic assistant named Soupy Dafoe obsessed with soup"`). It is injected into `BASE_SYSTEM_PROMPT` at call time in `generate_gpt_response` and `analyze_image`. Personality descriptors should be short — the base prompt handles all boilerplate rules.

On startup, `bot.chatgpt_behaviour` is set via `PersonalityManager.get_active()`, which reads `ACTIVE_PERSONALITY=` from `.env` (falls back to index 0 if not yet set). Any `!change` or `/personality change` call updates `bot.chatgpt_behaviour` and persists the selection to `.env` via `set_active()`.

Per-channel pins override the global personality for a specific channel. `on_message` resolves `channel_behaviour = get_channel_personality(channel_id) or bot.chatgpt_behaviour` and passes that to `generate_gpt_response` and `analyze_image`. Pins are stored in `data/channel_personalities.json`.

## RAG Memory System

Per-channel persistent memory backed by ChromaDB (`data/chroma/`). Every qualifying message the bot processes in an allowed channel is stored. Before each response, a semantic search retrieves relevant past messages and document chunks, which are injected into the system prompt as `RELEVANT CONTEXT FROM MEMORY`.

**Two document types in each collection:**
- `message` — a stored Discord message (role + content); image analysis results stored here too as tagged entries
- `document` — a chunk from an uploaded file or `!learn` text

**Chunk size:** 3000 chars, 300-char overlap. Most small-to-medium files fit in one chunk.

**Quality filter:** user messages are checked before storage — messages under 8 chars, pure emoji/URL content, and known filler phrases (`lol`, `ok`, `yeah`, etc.) are discarded. Bot responses always stored.

**Retrieval:** candidates retrieved up to the configured k, then filtered by cosine distance threshold (`DISTANCE_THRESHOLD`, read from `.env`, default 0.8). Results above threshold are dropped. Tune via `.env` to adjust noise vs. recall.

**Message expiry:** chat messages tagged with `expires_at = now + MESSAGE_TTL_DAYS * 86400` at write time. Retrieval filters out expired entries in Python (safe for legacy entries without the field). Documents (`expires_at=0`) never expire.

**Deduplication:** all stored entries use stable Discord message IDs as ChromaDB document IDs. ChromaDB upsert semantics ensure re-processing the same message never creates duplicates.

**Context per response:**
- `HISTORYLENGTH` messages via `fetch_message_history` (direct Discord API)
- `RAG_MESSAGE_CONTEXT` semantically relevant messages from ChromaDB (filtered by distance)
- 5 relevant document chunks from ChromaDB (filtered by distance)

**Supported file types:** `.txt .py .md .js .ts .jsx .tsx .json .csv .yaml .yml .html .css .sh .toml .ini .cfg .pdf`

## Architecture Overview

`main.py` is the entry point (~30 lines). It initialises a `bridge.Bot`, sets shared state on the bot object, loads all Cogs via `bot.load_extension()`, and calls `bot.run()`. All commands and event handlers live in `cogs/`.

### Cog Layout

- **`cogs/chat.py`** — `ChatCog`: `on_message` enqueues into a per-channel `asyncio.Queue`, `_process_queue` drains it sequentially via `_handle_message` (prevents concurrent processing races per channel). `on_reaction_add` (gated by `REACTION_RESPONSES` env var), `on_ready`, `on_command_error`. `_should_respond()`: always responds to @mentions, responds in `CHANNEL_IDS` channels unless directed at a specific human. Defines `_GENERATE_TOOL` and `_TRANSFORM_TOOL` OpenAI tool schemas; the transform tool is only included in the tools list when the channel has a prior image in `bot.channel_image_state`.
- **`cogs/images.py`** — `ImagesCog`: `generate`, `transform`, `image` commands. `transform` has a separate `@commands.command()` for prefix (reads `ctx.message.attachments`) and a `@discord.slash_command()` for slash (takes explicit `attachment` option).
- **`cogs/personality.py`** — `PersonalityCog`: `!new`, `!change`, `!list`, `!pin`, `!unpin` prefix commands and `/personality` slash command group (new/change/list/remove/pin/unpin).
- **`cogs/games.py`** — `GamesCog`: `game` (Tic-Tac-Toe), `snake`, and `adventure` commands.
- **`cogs/servers.py`** — `ServersCog`: `minecraft` bridge command; Valheim prefix commands + `/valheim start|stop|status` slash group; Enshrouded prefix commands + `/enshrouded start|stop` slash group.
- **`cogs/fun.py`** — `FunCog`: `commands` (category help menu with buttons), `prompt` and `sandwich` bridge commands; `simulate` has a separate prefix command (flexible `*args`) and slash command (explicit `topic`, `p1`, `p2` params).
- **`cogs/rag.py`** — `RAGCog`: `learn` (prefix + slash, supports file attachment), `memory`, `cleardocs`, and `summarize` (bridge commands), `clearall` (prefix only, requires Manage Messages).

### Slash vs Prefix

Most commands use `@bridge.bridge_command()` which creates both a `!prefix` and `/slash` command automatically. Exceptions where bridge doesn't work cleanly:
- **`transform`**: prefix uses `ctx.message.attachments`; slash uses a `discord.Attachment` option
- **`simulate`**: prefix uses `*args` (flexible `[p1] [p2] <topic>`); slash has explicit typed params
- **`learn`**: prefix reads `ctx.message.attachments`; slash has an explicit `discord.Attachment` option

### Support Modules

- **`AIfunc/responses.py`** — `BASE_SYSTEM_PROMPT` constant; `generate_gpt_response()` (accepts optional `rag_context: list[str]` and `tools: list` for OpenAI tool calling — returns `(content, tool_calls)` tuple when tools are provided, plain string otherwise), `analyze_image()`, `generate_image()`, `transform_image()`.
- **`AIfunc/simulate.py`** — `ConversationSimulator`.
- **`chatbotfunc/logger.py`** — `setup_logging()`: configures the `bot` logger hierarchy. Console handler at INFO; `RotatingFileHandler` to `data/bot.log` (5MB × 3 backups) at `LOG_LEVEL` (default `WARNING`). Called once from `main.py`; all modules get a child logger via `logging.getLogger("bot.<module>")`.
- **`chatbotfunc/utils.py`** — `fetch_message_history()`, `async_chat_completion()`, `split_message()`, `format_error_message()`, `encode_discord_image()`.
- **`chatbotfunc/personalitymanager.py`** — `PersonalityManager`: reads/writes/manages personality descriptors from `.env`. `get_active()` / `set_active()` persist the selected personality via `ACTIVE_PERSONALITY=`. `get_channel_personality()` / `set_channel_personality()` / `clear_channel_personality()` manage per-channel pins stored in `data/channel_personalities.json`.
- **`ragfunc/memory.py`** — `ChannelMemory` class (ChromaDB wrapper); `store_message()` (with quality filter via `_should_store()`), `store_document()`, `retrieve()` (with `DISTANCE_THRESHOLD` cosine filter), `clear_documents()`, `clear_all()`; async helpers: `async_store_message`, `async_store_document`, `async_retrieve`, `async_count`, `async_clear_documents`, `async_clear_all`.
- **`gamefunc/adventure.py`** — `AdventureGame` class and map data. 55×23 grid dungeon built programmatically from room + corridor rectangles. 8-directional movement, items at (x,y) positions rendered as roguelike symbols, viewport rendering (33×15) centered on player. Win condition: pick up the Golden Crown.
- **`gamefunc/adventure_panel.py`** — `AdventureView(discord.ui.View)`: 3×3 D-pad (8 directions), Pick Up / Inventory / Look / Quit buttons. Direction buttons disable when adjacent tile is a wall. Embed refreshes in place on every action. Timeout clears `bot.active_games`.
- **`gamefunc/minecraft.py`** — Thread-safe async RCON using `socket.settimeout()` (not the `mcrcon` library, which uses `signal.alarm()` and crashes outside the main thread).
- **`gamefunc/minecraft_panel.py`** — `MinecraftPanel` Discord UI with live status embed and button enable/disable rules.
- **`gamefunc/valheim.py`** — `ValheimServer`, `EnshroudedServer` (Windows-only).
- **`funfunc/`** — Image search (Google CSE), web search (`web_search.py`, Tavily-backed — used by the AI `google_search` tool), GPT search prompt, sandwich generator.

### Shared State

All mutable state lives on the bot object, accessible from any Cog via `self.bot`:

- `bot.chatgpt_behaviour` — Active personality descriptor string; changed by `!change` / `/personality change`
- `bot.active_games` — `dict[channel_id, bool]` prevents message handling during in-channel games
- `bot.channel_image_state` — `dict[channel_id, {"last_generated": bytes|None, "last_transformed": bytes|None}]` tracks the most recent generated and transformed image per channel. `last_transformed` is preferred over `last_generated` when picking an image to transform (enables chaining). Set by `!generate`, `!transform`, and the AI image tools in `chat.py`.
- `bot.personality_manager` — `PersonalityManager` instance

### Message Flow

`on_message` in `ChatCog`:
1. Returns early if message is from the bot itself
2. Returns early for `!`-prefixed messages (bot routes commands automatically via `bridge.Bot`)
3. Skips channels with active games
4. Enqueues message into the channel's `asyncio.Queue`; starts a worker task for the channel if one isn't already running
5. Worker calls `_handle_message` sequentially — one message at a time per channel, different channels process independently
6. Resolves `channel_behaviour` = channel pin (if set) or global `bot.chatgpt_behaviour`
7. Processes image attachments via `analyze_image()` if present in an allowed channel; sends response, then stores both the user prompt and analysis result in RAG as tagged message entries using real Discord message IDs
8. If a supported file is attached, downloads it, stores in ChromaDB via `async_store_document`, breaks
9. Calls `_should_respond()`: True if bot is @mentioned (any channel) OR if channel is in `CHANNEL_IDS` and no human @mentions are present
10. Stores user message in ChromaDB via `async_store_message` (filtered by `_should_store()` — junk skipped)
11. Retrieves RAG context: top-5 document chunks + top-`RAG_MESSAGE_CONTEXT` message chunks, both filtered by `DISTANCE_THRESHOLD`
12. Fetches direct Discord history via `fetch_message_history`, appends user message
13. Builds tools list: `_GENERATE_TOOL` and `_SEARCH_TOOL` always included; `_TRANSFORM_TOOL` added only if `bot.channel_image_state` has a prior image for this channel
14. Calls `generate_gpt_response()` with RAG context, tools, and `auto_resolve={"google_search": _execute_search}`; receives `(content, tool_calls)` tuple. The `google_search` tool is resolved *inside* `generate_gpt_response` (Tavily call + a second API call so the model sees results); only image tool calls are returned to the caller
15. For each returned tool call: `generate_image` → calls `generate_image()`, posts as `discord.File`, stores `last_generated` in channel state; `transform_image` → calls `transform_image()` on `last_transformed or last_generated`, posts result, stores `last_transformed`
16. If the model also returned text content, sends it as normal chunked message and stores in ChromaDB

### Bot Commands Reference

| Prefix | Slash | Description |
|---|---|---|
| `!generate <prompt>` | `/generate` | Generate an image via gpt-image-1 |
| `!transform <instructions>` | `/transform` | Transform an image |
| `!transform last <instructions>` | `/transform use_last:True` | Transform the most recent image in this channel (last transformed, or last generated if no transform yet) |
| `!image <query>` | `/image` | Search and display an image with AI description |

| `!change [n]` | — | Switch to personality #n or random |
| `!new <descriptor>` | — | Add a new personality descriptor |
| `!list` | — | List available personalities |
| — | `/personality change\|new\|list\|remove` | Personality slash commands |
| `!simulate [p1] [p2] <topic>` | `/simulate` | Simulate conversation between two personalities |
| `!game X\|O` | `/game` | Play Tic-Tac-Toe |
| `!snake` | `/snake` | Play Snake |
| `!adventure` | `/adventure` | ASCII dungeon game (QUD-style grid map, 8-directional movement) |
| `!minecraft` | `/minecraft` | Open the Minecraft server management panel |
| `!start_valheim` / `!stop_valheim` | `/valheim start\|stop\|status` | Manage Valheim server |
| `!start_enshrouded` / `!stop_enshrouded` | `/enshrouded start\|stop` | Manage Enshrouded server |
| `!commands` | `/commands` | Browse all bot commands by category (button menu) |
| `!prompt <topic>` | `/prompt` | Generate a Google search URL for a topic |
| `!sandwich` | `/sandwich` | Generate a random sandwich |
| `!pin [n]` | `/personality pin [n]` | Pin personality #n to this channel |
| `!unpin` | `/personality unpin` | Remove channel personality pin |
| `!learn [text]` | `/learn` | Store text or file in RAG memory |
| `!memory` | `/memory` | Show memory stats for this channel |
| `!summarize` | `/summarize` | TL;DR of recent conversation in this channel |
| `!cleardocs` | `/cleardocs` | Clear stored documents (keeps message history) |
| `!clearall` | — | Wipe all memory for this channel (Manage Messages required) |
