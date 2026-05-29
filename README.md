# Discord Bot

A personal Discord bot with GPT chat, image generation and transformation, game server management, in-channel mini-games, and persistent RAG memory.

## Features

- **GPT chat** — responds in allowed channels using a configurable personality/system prompt; always responds to direct @mentions; per-channel message queue prevents concurrent processing races
- **RAG memory** — per-channel persistent memory backed by ChromaDB; stores chat history and uploaded documents, retrieves semantically relevant context on every response
- **Image generation** — gpt-image-1 image generation via `!generate` / `/generate`, or naturally in conversation ("make me a picture of a crab")
- **Image transformation** — native image editing via `!transform` / `/transform`, or naturally in conversation ("make it blue"); per-channel image state enables chaining transforms
- **Image analysis** — describe attached images in chat, or search and describe via `!image` / `/image`
- **Web search** — bot looks up current information in conversation via tool calling (Tavily); incorporates live results into its in-character response
- **Personality system** — short character descriptors injected into a shared base system prompt; switchable at runtime, pinnable per-channel, persists across restarts
- **Conversation simulation** — two bot personalities argue a topic via `!simulate` / `/simulate`
- **Mini-games** — Tic-Tac-Toe (`!game` / `/game`), Snake (`!snake` / `/snake`), and a QUD-style ASCII dungeon (`!adventure` / `/adventure`) with an 8-directional grid map, items, and a win condition
- **Game server management** — Minecraft (vanilla & modded) panel with live status; Valheim and Enshrouded server commands
- **Slash commands** — every command available as both `!prefix` and `/slash`
- **Cog-based architecture** — each feature domain lives in its own `cogs/` module, hot-reloadable at runtime

## Requirements

- Python 3.10+
- kitty terminal (for Minecraft server launch on Linux)

Install Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Setup

A single **`.env`** file at the project root holds all configuration.

```env
# ─────────────────────────────────────────────
# Discord
# ─────────────────────────────────────────────

# Bot token from the Discord Developer Portal (Bot tab)
DISCORD_TOKEN=your_discord_bot_token

# Comma-separated channel IDs the bot listens in and responds to automatically.
# The bot will always respond to direct @mentions regardless of this list.
CHANNEL_IDS=123456789,987654321


# ─────────────────────────────────────────────
# OpenAI
# ─────────────────────────────────────────────

# OpenAI API key
OPENAI_API_KEY=your_openai_api_key

# Model used for chat completions and personality responses
MODEL_CHAT=gpt-4o

# Max tokens for normal chat responses
MAX_TOKENS=500

# Enable or disable reaction responses (true/false).
# When true, the bot responds to emoji reactions on its own messages.
# Set to false to prevent reaction spam without losing the feature.
REACTION_RESPONSES=true

# Python logging level for data/bot.log (DEBUG / INFO / WARNING / ERROR).
# Console always shows INFO+. Leave at WARNING for production; use DEBUG when hunting bugs.
LOG_LEVEL=WARNING


# ─────────────────────────────────────────────
# Chat History & RAG Memory
# ─────────────────────────────────────────────

# Number of recent Discord messages fetched directly from the channel per response.
# These form the immediate conversation window the bot always sees.
HISTORYLENGTH=30

# Number of semantically relevant past messages retrieved from ChromaDB per response.
# These are filtered by cosine distance — only truly relevant ones are injected.
RAG_MESSAGE_CONTEXT=50

# How many days a chat message stays retrievable from RAG memory.
# After this period it is excluded from retrieval (but not deleted from the DB).
# Documents stored via !learn never expire.
MESSAGE_TTL_DAYS=30

# Cosine distance cutoff for RAG retrieval (range 0–2; lower = more similar).
# Results above this threshold are dropped as too dissimilar to be useful.
# Lower values = stricter / fewer results. Raise if relevant context is being missed.
DISTANCE_THRESHOLD=0.8


# ─────────────────────────────────────────────
# Google Search
# ─────────────────────────────────────────────

# Google Custom Search API key — used by !image and !prompt commands
GOOGLE_API_KEY=your_google_api_key

# Google Custom Search Engine ID — configure at programmablesearchengine.google.com
GOOGLE_CSE_ID=your_cse_id


# ─────────────────────────────────────────────
# Web Search (Tavily)
# ─────────────────────────────────────────────

# Tavily API key — powers the AI web search tool (bot looks things up in conversation).
# Free tier, no credit card — sign up at tavily.com. Leave blank to disable web search.
TAVILY_API_KEY=tvly-your_tavily_key


# ─────────────────────────────────────────────
# Minecraft Servers
# ─────────────────────────────────────────────

# Vanilla server — path to server directory (for start/stop scripts)
MINECRAFT_VANILLA_DIR=/home/user/minecraft/vanilla
MINECRAFT_VANILLA_RCON_HOST=localhost
MINECRAFT_VANILLA_RCON_PORT=25575
MINECRAFT_VANILLA_RCON_PASSWORD=your_rcon_password

# Modded server — same structure as vanilla
MINECRAFT_MODDED_DIR=/home/user/minecraft/modded
MINECRAFT_MODDED_RCON_HOST=localhost
MINECRAFT_MODDED_RCON_PORT=25575
MINECRAFT_MODDED_RCON_PASSWORD=your_rcon_password


# ─────────────────────────────────────────────
# Valheim & Enshrouded (Windows only)
# ─────────────────────────────────────────────

# Valheim dedicated server — Windows batch file launch, will fail on Linux
VALHEIM_SERVER_NAME=MyValheimServer
VALHEIM_WORLD_NAME=MyWorld
VALHEIM_PASSWORD=your_password
VALHEIM_PORT=2456
VALHEIM_STEAM_DIR=I:\SteamLibrary

# Enshrouded dedicated server — Windows executable launch, will fail on Linux
ENSHROUDED_EXE=I:\SteamCMD\steamapps\common\enshrouded_server\enshrouded_server.exe


# ─────────────────────────────────────────────
# Personalities
# ─────────────────────────────────────────────

# One short character descriptor per line — all use the same key.
# Each is injected into BASE_SYSTEM_PROMPT at the {personality} slot.
# Managed at runtime via !new, !change, !list, and /personality commands.
PERSONALITY=a sarcastic assistant named Soupy Dafoe obsessed with soup
PERSONALITY=an enthusiastic valley girl with a secret PhD in Astrophysics named Tiffany

# Last selected personality — written automatically by !change / /personality change
ACTIVE_PERSONALITY=a sarcastic assistant named Soupy Dafoe obsessed with soup
```

Personalities are short character descriptors injected into `BASE_SYSTEM_PROMPT`. The base prompt handles all platform rules so descriptors only need to describe the character. The active personality persists across restarts via `ACTIVE_PERSONALITY=`. Use `!pin` / `/personality pin` to lock a specific personality to a channel permanently. Managed at runtime via `!new`, `!list`, `!change`, and `/personality` slash commands.

## Running

```bash
source .venv/bin/activate
python main.py
```

## Commands

All commands are available as both `!prefix` and `/slash`. The table below shows both forms.

### Chat & Personality

| Prefix | Slash | Description |
|---|---|---|
| `!change [n]` | — | Switch to personality #n, or pick randomly |
| `!new <text>` | — | Add a new personality descriptor |
| `!list` | — | List all personalities as a file |
| `!pin [n]` | `/personality pin [n]` | Pin personality #n to this channel permanently |
| `!unpin` | `/personality unpin` | Remove the channel personality pin |
| — | `/personality change [n]` | Switch personality |
| — | `/personality new <text>` | Add a new personality |
| — | `/personality list` | List personalities |
| — | `/personality remove <n>` | Remove personality at index n |

### Memory (RAG)

| Prefix | Slash | Description |
|---|---|---|
| `!learn <text>` | `/learn` | Store text directly in memory |
| `!learn` + attachment | `/learn` + file | Store a file in memory (.txt, .py, .md, .pdf, .json, .csv, and more) |
| `!memory` | `/memory` | Show how many chunks are stored for this channel |
| `!summarize` | `/summarize` | TL;DR of the recent conversation in this channel |
| `!cleardocs` | `/cleardocs` | Remove all stored documents (keeps message history) |
| `!clearall` | — | Wipe all memory for this channel (requires Manage Messages) |

### Images

| Prefix | Slash | Description |
|---|---|---|
| `!generate <prompt>` | `/generate <prompt>` | Generate an image with gpt-image-1 |
| `!transform <instructions>` | `/transform` | Transform an attached image |
| `!transform last <instructions>` | `/transform use_last:True` | Transform the most recent image in this channel |
| `!image <query>` | `/image <query>` | Search Google Images and describe the result |
| *(natural language)* | — | Ask the bot to generate or transform an image in conversation |


### Games

| Prefix | Slash | Description |
|---|---|---|
| `!game X\|O` | `/game` | Play Tic-Tac-Toe (choose your symbol) |
| `!snake` | `/snake` | Play Snake (w/a/s/d to move) |
| `!adventure` | `/adventure` | ASCII dungeon (QUD-style grid, 8-directional movement, items, win condition) |

### Game Servers

| Prefix | Slash | Description |
|---|---|---|
| `!minecraft` | `/minecraft` | Open the Minecraft server panel |
| `!start_valheim` | `/valheim start` | Start the Valheim dedicated server |
| `!stop_valheim` | `/valheim stop` | Stop the Valheim dedicated server |
| `!valheim_status` | `/valheim status` | Check Valheim server status |
| `!start_enshrouded` | `/enshrouded start` | Start the Enshrouded dedicated server |
| `!stop_enshrouded` | `/enshrouded stop` | Stop the Enshrouded dedicated server |

### Misc

| Prefix | Slash | Description |
|---|---|---|
| `!simulate [p1] [p2] <topic>` | `/simulate` | Simulate a conversation between two personalities |
| `!prompt <topic>` | `/prompt <topic>` | Generate a Google search URL for a topic via GPT |
| `!sandwich` | `/sandwich` | Generate a random sandwich |

## Architecture

```
main.py                     — bot init, shared state, load_extension calls, bot.run()
cogs/
  chat.py                   — on_message, on_reaction_add, on_ready (GPT chat handler, RAG integration, AI image tools)
  images.py                 — generate, transform, image, variation commands
  personality.py            — prefix + slash personality commands
  games.py                  — game (Tic-Tac-Toe), snake, adventure commands
  servers.py                — minecraft, valheim, enshrouded server commands
  fun.py                    — prompt, simulate, sandwich commands
  rag.py                    — learn, memory, cleardocs, clearall commands
AIfunc/
  responses.py              — BASE_SYSTEM_PROMPT constant; OpenAI wrappers:
                              generate_gpt_response (accepts rag_context + tools;
                              returns (content, tool_calls) tuple when tools provided),
                              analyze_image, generate_image, transform_image
  simulate.py               — ConversationSimulator
chatbotfunc/
  logger.py                 — setup_logging(): RotatingFileHandler → data/bot.log,
                              console at INFO, file at LOG_LEVEL (default WARNING)
  utils.py                  — fetch_message_history, async_chat_completion,
                              split_message, format_error_message, encode_discord_image
  personalitymanager.py     — PersonalityManager (reads/writes .env; get/set_active for persistence; get/set/clear_channel_personality for per-channel pins)
gamefunc/
  adventure.py              — AdventureGame: 55×23 grid dungeon, 8-dir movement,
                              item positions, viewport renderer (33×15)
  adventure_panel.py        — AdventureView: D-pad buttons, embed-in-place refresh,
                              timeout cleanup
  minecraft.py              — MinecraftServer (thread-safe async RCON, no signal module)
  minecraft_panel.py        — MinecraftPanel Discord UI (buttons, live status)
  valheim.py                — ValheimServer, EnshroudedServer (Windows batch/exe)
  tictactoe.py              — play_tic_tac_toe
  snake.py                  — SnakeGame
ragfunc/
  memory.py                 — ChannelMemory (ChromaDB wrapper); store_message, store_document,
                              retrieve, clear methods; async helpers
funfunc/
  image_search.py           — Google Custom Search API wrapper (image search)
  web_search.py             — Tavily web search wrapper (AI google_search tool)
  prompt.py                 — GPTSearchPrompt
  sandwich.py               — random sandwich generator
data/
  chroma/                   — ChromaDB persistent vector store (auto-created, gitignored)
  channel_personalities.json — per-channel personality pin map (auto-created, gitignored)
```

## RAG Memory System

Every qualifying message the bot processes is stored in a per-channel ChromaDB collection on disk (`data/chroma/`). Before generating any response, the bot runs a semantic similarity search and injects the most relevant past messages and document chunks into the system prompt. This gives the bot long-term memory without bloating the token window with raw history.

**How context works per response:**
- Last `HISTORYLENGTH` messages (default: 30) fetched directly from Discord — the immediate conversation window
- Top `RAG_MESSAGE_CONTEXT` semantically relevant past messages retrieved from ChromaDB (default: 50), filtered by cosine distance — long-term memory
- Top 5 relevant document chunks from any stored files, filtered by cosine distance — knowledge base

**Quality filter:** low-value user messages (under 8 chars, pure emoji, known filler like `lol` / `ok` / `yeah`) are discarded before storage. Bot responses and image analysis results are always stored.

**Deduplication:** stored entries use Discord message IDs as ChromaDB document IDs — re-processing the same message never creates duplicates.

**Image analysis:** when you share an image in an allowed channel, the bot's description is stored in RAG so it can reference past images in future conversations.

**Supported file types for `!learn`:**
`.txt` `.py` `.md` `.js` `.ts` `.jsx` `.tsx` `.json` `.csv` `.yaml` `.yml` `.html` `.css` `.sh` `.toml` `.ini` `.cfg` `.pdf`

PDFs are text-extracted via `pypdf`. Scanned/image-only PDFs won't have extractable text.

**Message expiry:** chat messages are tagged with an expiry timestamp at write time (`MESSAGE_TTL_DAYS`, default 30). Expired messages are excluded from retrieval but not deleted from the DB. Documents stored via `!learn` never expire.

**Memory is per-channel** — each Discord channel has its own isolated collection. `!clearall` only affects the current channel.

## Personality System

`BASE_SYSTEM_PROMPT` in `AIfunc/responses.py` defines platform-level rules that apply to every personality:
- Discord context (concise, conversational responses)
- Code block formatting
- History handling (focus on recent, use history as context)
- Stay in character directive

Each `PERSONALITY=` line in `.env` is a short character descriptor injected at the `{personality}` slot. Examples:
- `a sarcastic, reluctant assistant named Soupy Dafoe preoccupied with soup`
- `Professor Hubert J. Farnsworth from Futurama — exclamatory, brilliantly absent-minded`
- `a DnD-style Sorceress who must roll a dice and announce the result before any action`

The active personality persists across restarts — `ACTIVE_PERSONALITY=` is written to `.env` automatically on every `!change` or `/personality change`.

Use `!pin [n]` / `/personality pin [n]` to lock a specific personality to a channel. Pinned channels always use that personality regardless of the global selection. Pins are stored in `data/channel_personalities.json` and survive restarts. Remove with `!unpin` / `/personality unpin`.

## Known Limitations

- **Valheim / Enshrouded commands** are Windows-only (use `.bat` files and `CREATE_NEW_CONSOLE`). They will fail on Linux.
- **`!transform last` / AI transform** requires at least one `!generate` or `!transform` call in the current session — image bytes are stored per-channel in memory and not persisted across restarts.
- **Scanned PDFs** — `!learn` can only extract text from text-based PDFs. Image-only scans won't work.
- **Re-uploading files** — if a file was stored before the chunk size was increased to 3000 chars, re-upload it with `!learn` to get better chunking.
- **RAG distance threshold** — `DISTANCE_THRESHOLD` (default `0.8`) is set in `.env`. If relevant context is being dropped, raise it; if too much noise is coming through, lower it. Range is 0–2.
- **RAG message expiry** — expired messages are excluded from retrieval but remain in the DB. Run `!clearall` to fully purge a channel's history if the DB grows large.
