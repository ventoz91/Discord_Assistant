# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
source .venv/bin/activate
python main.py
```

## Environment Configuration

All configuration lives in **`.env`** at the project root. All values are read at call time (not module load), so changes take effect on the next request without restarting.

**Core**
- `DISCORD_TOKEN` — Discord bot token
- `OPENAI_API_KEY` — OpenAI API key
- `MODEL_CHAT` — OpenAI model for chat completions (e.g. `gpt-4o`)
- `CHANNEL_IDS` — Comma-separated Discord channel IDs the bot listens to
- `MAX_TOKENS` — Max completion tokens for responses (default: 500)
- `TEMPERATURE` — Response creativity, 0.0–2.0 (default: 1.5)
- `IMAGE_SIZE` — Image dimensions: `1024x1024` / `1536x1024` / `1024x1536` (default: `1024x1024`)
- `IMAGE_QUALITY` — `low` / `medium` / `high` (default: `medium`)
- `ANALYZE_MAX_TOKENS` — Token cap for image analysis (default: 500)
- `REACTION_RESPONSES` — `true` / `false` — emoji reaction responses (default: `true`)
- `LOG_LEVEL` — File log level: `DEBUG` / `INFO` / `WARNING` / `ERROR` (default: `WARNING`). Console always shows INFO+.

**RAG Memory**
- `HISTORYLENGTH` — Recent Discord messages fetched directly per response (default: 30)
- `RAG_MESSAGE_CONTEXT` — Older messages retrieved from ChromaDB per response (default: 50). Restricted to entries older than the history window.
- `RAG_DOC_CONTEXT` — Document chunks retrieved per response (default: 5)
- `MESSAGE_TTL_DAYS` — Days before a chat message is excluded from retrieval (default: 30). Documents never expire.
- `DISTANCE_THRESHOLD` — Cosine distance cutoff for retrieval (default: 0.8). Results above this are dropped.
- `RAG_DECAY_HALFLIFE_DAYS` — Recency decay half-life for message scoring (default: 14). A message this many days old needs to be twice as similar to survive the threshold. Set to 0 to disable. Documents are never decayed.
- `MAX_CONTEXT_TOKENS` — Optional hard token budget (chars÷4 estimate). Trims RAG messages from the tail, then docs, if exceeded. Unset by default.

**User Profiles**
- `USER_PROFILE_EXTRACTION` — `true` / `false` (default: `true`). Profiles stored in `data/user_profiles.json` (gitignored).
- `USER_PROFILE_MAX_FACTS` — Max facts stored per user (default: 20). Oldest dropped at cap.
- `USER_PROFILE_INJECT_MAX` — Max facts injected per call (default: 10). Most recent preferred.
- `USER_PROFILE_MODEL` — Model for extraction (default: `MODEL_CHAT`). A cheaper model works fine.
- `USER_PROFILE_EXTRACT_TOKENS` — Max tokens for the extraction response (default: 200).
- `USER_PROFILE_MSG_CHARS` — Max chars of user/bot message fed to extraction (default: 500).

**Auto-Summarization**
- `SUMMARY_ENABLED` — `true` / `false` (default: `true`)
- `SUMMARY_INTERVAL_HOURS` — Scan interval in hours (default: 24)
- `SUMMARY_MIN_NEW_MESSAGES` — Minimum expiring messages to trigger summarization (default: 10). Below this, skip unless forced.
- `SUMMARY_FORCE_AFTER_DAYS` — Force a summary after this many days without one, regardless of count (default: 5).
- `SUMMARY_DAYS_BEFORE_EXPIRY` — Summarize messages this many days before their TTL (default: 5).
- `SUMMARY_MODEL` — Model for summarization (default: `MODEL_CHAT`).
- `SUMMARY_MAX_TOKENS` — Max tokens in summary output (default: 500).
- `SUMMARY_MAX_INPUT_CHARS` — Max chars of chat fed to summarizer (default: 12000).

**External Services**
- `GOOGLE_API_KEY` — Google Custom Search API key (used by `!image`)
- `GOOGLE_CSE_ID` — Google Custom Search Engine ID (used by `!image`)
- `TAVILY_API_KEY` — Tavily API key for AI web search tool in `chat.py`

**Game Servers**
- `MINECRAFT_VANILLA_DIR` / `MINECRAFT_VANILLA_RCON_HOST` / `MINECRAFT_VANILLA_RCON_PORT` / `MINECRAFT_VANILLA_RCON_PASSWORD`
- `MINECRAFT_VANILLA_SSH_HOST` — remote host for vanilla start via SSH+Docker (required for start to work)
- `MINECRAFT_VANILLA_SSH_USER` — optional SSH username; defaults to current user
- `MINECRAFT_VANILLA_COMPOSE_DIR` — path to docker-compose on remote host (default: `/home/data`)
- `MINECRAFT_MODDED_DIR` / `MINECRAFT_MODDED_RCON_HOST` / `MINECRAFT_MODDED_RCON_PORT` / `MINECRAFT_MODDED_RCON_PASSWORD`
- `VALHEIM_SERVER_NAME` / `VALHEIM_WORLD_NAME` / `VALHEIM_PASSWORD` / `VALHEIM_PORT` / `VALHEIM_STEAM_DIR`
- `ENSHROUDED_EXE`
- `SATISFACTORY_SSH_HOST` — required; remote host to SSH into for start/stop
- `SATISFACTORY_SSH_USER` — optional SSH username
- `SATISFACTORY_COMPOSE_DIR` — path to docker-compose on remote host (default: `/home/data`)
- `SATISFACTORY_API_HOST` — host for HTTPS API calls (default: `SATISFACTORY_SSH_HOST`)
- `SATISFACTORY_API_PORT` — API port (default: `7777`)

**Personalities (legacy — migration only)**
- `PERSONALITY=<descriptor>` — Read once on first run to populate `data/personalities.json`. After migration, ignored.
- `ACTIVE_PERSONALITY=<descriptor>` — Read once on first run. After migration, ignored.

## Personality System

`BASE_SYSTEM_PROMPT` in `AIfunc/responses.py` is the shared system prompt. It establishes: Discord platform context, no hollow filler openers, code block formatting, RAG context handling (treat as background knowledge, never announce), history handling (focus on recent, use history as context), stay-in-character, and uncertainty handling.

**Storage:** personalities live in `data/personalities.json` as a list of plain text descriptor strings plus an `"active"` key. `PersonalityManager` reads/writes only this file. On first run it auto-migrates `PERSONALITY=` and `ACTIVE_PERSONALITY=` entries from `.env` — existing personalities are preserved, `.env` entries are then ignored.

`bot.chatgpt_behaviour` holds the active descriptor. It is injected at `{personality}` in `BASE_SYSTEM_PROMPT` at call time in `generate_gpt_response` and `analyze_image`. Descriptors should be short — the base prompt handles all boilerplate.

Per-channel pins override the global personality. `channel_behaviour = get_channel_personality(channel_id) or bot.chatgpt_behaviour` is resolved in `_handle_message` and `_handle_reaction`. Pins are cached in memory on `PersonalityManager` (invalidated on write) and persisted to `data/channel_personalities.json`.

## RAG Memory System

Per-channel ChromaDB collections in `data/chroma/`. Singleton client (`_get_client()` in `memory.py`) shared across all calls.

**Two document types per collection:**
- `message` — stored Discord message (`role: content`); image analysis results stored as tagged entries
- `document` — chunk from `!learn` text or uploaded file; never expires (`expires_at=0`)

**Chunk size:** 3000 chars, 300-char overlap.

**Storage quality filter (`_should_store`):** user messages under 8 chars, pure emoji/URL content, and known filler phrases are discarded. Bot replies under 40 chars are also discarded. Longer bot responses always stored.

**Context threading:** `store_message()` accepts an optional `context_snippet` (≤200 chars of the preceding message), stored in metadata. Retrieved entries display it as `[re: ...]` prefix so the model understands what prompted each memory.

**Retrieval with decay:** `retrieve()` fetches `k×3` candidates, applies exponential recency decay to message-type entries (`effective_dist = dist / 2^(-age_days/halflife)`), filters by `DISTANCE_THRESHOLD`, re-sorts by adjusted distance, returns top k. Documents are never decayed.

**History/RAG deduplication:** RAG message retrieval uses `before_ts=history_cutoff_ts`, restricting results to entries older than the oldest message in the direct history window. The two context blocks carry disjoint sets.

**Message expiry:** tagged with `expires_at = now + MESSAGE_TTL_DAYS * 86400`. Retrieval skips expired entries. Auto-summarization condenses expiring messages into permanent documents before they lapse.

**Auto-summarization:** `summarizer_loop` (started in `on_ready`) wakes every `SUMMARY_INTERVAL_HOURS`. For each channel it fetches messages older than `(TTL - SUMMARY_DAYS_BEFORE_EXPIRY)` days. Skip if count < `SUMMARY_MIN_NEW_MESSAGES` AND last summary < `SUMMARY_FORCE_AFTER_DAYS` days ago; otherwise summarize, store as permanent document, delete originals.

**User profiles:** `get_user_context()` reads `data/user_profiles.json` and returns a formatted string of the user's most recent facts. Injected as `USER PROFILE:` section in the system prompt before RAG context. After each text exchange, `extract_and_update()` fires as a background `asyncio.create_task` to extract and merge new facts without blocking the response.

**Supported file types:** `.txt .py .md .js .ts .jsx .tsx .json .csv .yaml .yml .html .css .sh .toml .ini .cfg .pdf`

## Architecture Overview

`main.py` (~30 lines): initialises `bridge.Bot`, sets shared state, calls `bot.load_extension()` for all cogs, calls `bot.run()`.

### Cog Layout

- **`cogs/chat.py`** — `ChatCog`: queue-based message handling; `_enqueue()` pushes zero-arg callables onto per-channel `asyncio.Queue`; `_process_queue` drains sequentially. `on_message` and `on_reaction_add` both enqueue. `_handle_message` and `_handle_reaction` share the same flow: resolve personality, fetch history (with recency cutoff), retrieve RAG (decay-aware, history-deduplicated), fetch user profile, call `generate_gpt_response` with full tool set, handle tool calls, store response, fire background profile extraction. `on_ready` starts `summarizer_loop` task. Defines `_GENERATE_TOOL`, `_TRANSFORM_TOOL`, `_SEARCH_TOOL`, `_SUGGEST_TOOL`.
- **`cogs/images.py`** — `generate`, `transform`, `image` commands. `transform` has separate prefix (reads `ctx.message.attachments`) and slash (explicit `attachment` option) implementations.
- **`cogs/personality.py`** — `!new`, `!change`, `!list`, `!pin`, `!unpin` prefix commands and `/personality` slash group (new/change/list/remove/pin/unpin).
- **`cogs/games.py`** — `game` (Tic-Tac-Toe), `snake`, `adventure` commands.
- **`cogs/servers.py`** — `minecraft` bridge command; Valheim prefix + `/valheim start|stop|status` slash group; Enshrouded prefix + `/enshrouded start|stop` slash group.
- **`cogs/fun.py`** — `commands` and `help` bridge commands (both post the same formatted text list); `sandwich` bridge command; `simulate` has separate prefix (`*args`) and slash (explicit typed params) implementations.
- **`cogs/rag.py`** — `learn` (prefix + slash, file attachment support), `memory`, `cleardocs`, `summarize` (bridge commands), `clearall` (prefix only, requires Manage Messages).

### Slash vs Prefix

Most commands use `@bridge.bridge_command()`. Exceptions:
- **`transform`**: prefix reads `ctx.message.attachments`; slash takes explicit `discord.Attachment` option
- **`simulate`**: prefix uses `*args`; slash has explicit typed `topic`, `p1`, `p2` params
- **`learn`**: prefix reads `ctx.message.attachments`; slash takes explicit `discord.Attachment` option

### Support Modules

- **`AIfunc/responses.py`** — `BASE_SYSTEM_PROMPT`; `generate_gpt_response(message_history, personality, rag_context, user_context, tools, auto_resolve)` — returns `(content, tool_calls)` tuple when tools provided; `analyze_image(base64, instructions, history, personality, user_context)`; `generate_image()`; `transform_image()`. `user_context` injected as `USER PROFILE:` section before RAG context in system prompt.
- **`AIfunc/simulate.py`** — `ConversationSimulator`.
- **`chatbotfunc/logger.py`** — `setup_logging()`: console at INFO, `RotatingFileHandler` to `data/bot.log` (5 MB × 3 backups) at `LOG_LEVEL`.
- **`chatbotfunc/utils.py`** — `fetch_message_history(channel, bot, exclude_message_id, return_cutoff)` — optionally excludes one message ID and returns the oldest in-window timestamp as a recency cutoff; `async_chat_completion()`; `split_message()`; `format_error_message()`; `encode_discord_image()` (async, aiohttp); `SUPPORTED_DOC_EXTENSIONS` frozenset.
- **`chatbotfunc/personalitymanager.py`** — `PersonalityManager(env_path)`: `data/personalities.json` is the source of truth; auto-migrates from `.env` on first run; `get_active()` / `set_active()`; `get_channel_personality()` / `set_channel_personality()` / `clear_channel_personality()` with in-memory pin cache (invalidated on write).
- **`chatbotfunc/profiles.py`** — `get_user_context(user_id, display_name) -> str | None`: reads `data/user_profiles.json`, returns formatted fact string for system prompt injection. `extract_and_update(user_id, display_name, user_msg, bot_msg, model)`: async background task; sends extraction prompt to LLM, parses JSON array of new facts, merges into profile file.
- **`chatbotfunc/summarizer.py`** — `summarizer_loop(model)`: background coroutine; `summarize_channel(channel_id, model)`: fetches expiring messages, applies skip/force logic using `data/summarizer_state.json`, calls LLM, stores permanent summary document, deletes originals.
- **`ragfunc/memory.py`** — `ChannelMemory` (ChromaDB wrapper, singleton client via `_get_client()`): `store_message(role, content, message_id, context_snippet)`, `store_document(text, source)`, `retrieve(query, k, doc_type, before_ts)` (decay + threshold filter), `get_expiring(before_ts)`, `delete_by_ids(ids)`, `clear_documents()`, `clear_all()`; module-level `list_channel_ids()`; async helpers for all methods.
- **`gamefunc/adventure.py`** — `AdventureGame`: 55×23 grid dungeon, 8-dir movement, viewport renderer (33×15). Win: pick up the Golden Crown.
- **`gamefunc/adventure_panel.py`** — `AdventureView`: 3×3 D-pad, Pick Up / Inventory / Look / Quit. Direction buttons disable at walls. Embed refreshes in place.
- **`gamefunc/snake_panel.py`** — `SnakeView`: D-pad buttons, score tracking, embed-in-place.
- **`gamefunc/minecraft.py`** — Thread-safe async RCON using `socket.settimeout()` (avoids `signal.alarm()` crash outside main thread).
- **`gamefunc/minecraft_panel.py`** — `MinecraftPanel`: live status embed, button enable/disable rules.
- **`gamefunc/valheim.py`** — `ValheimServer`, `EnshroudedServer` (Windows-only).
- **`funfunc/`** — `image_search.py` (Google CSE), `web_search.py` (Tavily, used by `google_search` AI tool), `sandwich.py`.

### Shared State

All mutable state on the bot object, accessible from any Cog via `self.bot`:

- `bot.chatgpt_behaviour` — active personality descriptor string
- `bot.active_games` — `dict[channel_id, bool]` gates message handling during games
- `bot.channel_image_state` — `dict[channel_id, {"last_generated": bytes|None, "last_transformed": bytes|None}]`; `last_transformed` preferred for chaining
- `bot.personality_manager` — `PersonalityManager` instance

### Message Flow

`on_message` in `ChatCog`:
1. Early return if author is bot, message starts with `!`, or channel has active game
2. `_enqueue(channel_id, lambda: _handle_message(message))` — pushes callable onto per-channel queue; starts worker task if none running
3. Worker drains queue sequentially via `await coro_fn()` — one at a time per channel

`_handle_message`:
1. Resolve `channel_behaviour` = channel pin or `bot.chatgpt_behaviour`
2. Evaluate `should_respond` once (used for all three attachment/text paths)
3. Image attachment path: `analyze_image()`, send response, store user + analysis to RAG with message IDs, return
4. Document attachment path: download, `async_store_document`, break
5. Text path — `should_respond` gate:
   a. Fetch `message_history` with `return_cutoff=True` to get `history_cutoff_ts`
   b. Store user message to RAG with `context_snippet` = last assistant reply
   c. Retrieve `rag_docs` (no time filter) + `rag_msgs` (`before_ts=history_cutoff_ts`, decay-aware)
   d. Apply `MAX_CONTEXT_TOKENS` trim if set (tail of `rag_msgs` first, then `rag_docs`)
   e. Log estimated token count at DEBUG
   f. Fetch user profile: `get_user_context(author.id, author.display_name)`
   g. Build tools list: `[_GENERATE_TOOL, _SEARCH_TOOL, _SUGGEST_TOOL]` + `_TRANSFORM_TOOL` if channel has prior image
   h. Call `generate_gpt_response(history, personality, rag_context, user_context, tools, auto_resolve={google_search, suggest_activity})`
   i. `google_search` and `suggest_activity` auto-resolved internally; only image tool calls returned
   j. Handle `generate_image` / `transform_image` tool calls, post as `discord.File`, update `channel_image_state`
   k. Send text response in chunks, store to RAG with `context_snippet=message.content[:200]`
   l. `asyncio.create_task(extract_and_update(...))` — background profile extraction, never blocks

`on_reaction_add`: enqueues `_handle_reaction` through the same queue. `_handle_reaction` mirrors the text path (history cutoff, decay RAG, user profile, full tool set) and stores its response to RAG.

### Bot Commands Reference

| Prefix | Slash | Description |
|---|---|---|
| `!generate <prompt>` | `/generate` | Generate an image via gpt-image-1 |
| `!transform <instructions>` | `/transform` | Transform an attached image |
| `!transform last <instructions>` | `/transform use_last:True` | Transform the most recent image in this channel |
| `!image <query>` | `/image` | Search and display an image with AI description |
| `!change [n]` | `/personality change` | Switch to personality #n or random |
| `!new <descriptor>` | `/personality new` | Add a new personality descriptor |
| `!list` | `/personality list` | List available personalities |
| — | `/personality remove` | Remove a personality by index |
| `!pin [n]` | `/personality pin [n]` | Pin personality #n to this channel |
| `!unpin` | `/personality unpin` | Remove channel personality pin |
| `!simulate [p1] [p2] <topic>` | `/simulate` | Simulate conversation between two personalities |
| `!game X\|O` | `/game` | Play Tic-Tac-Toe |
| `!snake` | `/snake` | Play Snake |
| `!adventure` | `/adventure` | ASCII dungeon (QUD-style grid, 8-directional) |
| `!minecraft` | `/minecraft` | Minecraft server management panel |
| `!satisfactory` | `/satisfactory` | Satisfactory server management panel (SSH+Docker start/stop, HTTPS API status) |
| `!status` | `/status` | Live embed showing all game servers at a glance |
| `!start_valheim` / `!stop_valheim` | `/valheim start\|stop\|status` | Manage Valheim server |
| `!start_enshrouded` / `!stop_enshrouded` | `/enshrouded start\|stop` | Manage Enshrouded server |
| `!commands` / `!help` | `/commands` / `/help` | Show all bot commands (formatted text list) |
| `!sandwich` | `/sandwich` | Generate a random sandwich with AI image |
| `!learn [text]` | `/learn` | Store text or file in RAG memory |
| `!memory` | `/memory` | Show memory stats for this channel |
| `!summarize` | `/summarize` | TL;DR of recent conversation |
| `!cleardocs` | `/cleardocs` | Clear stored documents (keeps message history) |
| `!clearall` | — | Wipe all memory for this channel (Manage Messages required) |
