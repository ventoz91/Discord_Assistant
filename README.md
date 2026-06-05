# Discord Bot

A personal Discord bot with GPT chat, persistent long-term memory, per-user profiles, image generation and transformation, game server management, and in-channel mini-games.

## Features

- **GPT chat** — responds in configured channels and always to @mentions; in-character responses shaped by the active personality; per-channel message queue prevents concurrent processing races
- **Long-term RAG memory** — per-channel ChromaDB-backed memory; stores chat history and uploaded documents; semantically relevant context injected on every response; recency decay ensures old messages don't crowd out recent ones; RAG messages and direct history are kept deduplicated so nothing is sent to the model twice
- **User profiles** — after each exchange, a background LLM call extracts facts about the user (preferences, hobbies, games played, etc.) and stores them in `data/user_profiles.json`; the profile is injected into the system prompt so the bot genuinely knows who it's talking to
- **Auto-summarization** — a background task periodically condenses expiring messages into permanent summary documents before they vanish; effective memory is infinite; summaries survive indefinitely while raw message noise is cleaned up
- **Image generation** — gpt-image-1 via `!generate` / `/generate`, or naturally in conversation ("draw me a crab")
- **Image transformation** — AI image editing via `!transform` / `/transform`, or naturally in conversation ("make it blue"); transforms chain — each uses the previous result, not the original
- **Image analysis** — describe images attached in chat; search and describe via `!image` / `/image`
- **Web search** — Tavily-backed tool calling; the bot searches automatically when a question needs current info and incorporates results into its in-character response
- **Suggest activity** — when asked what to do, the bot randomly recommends a bot feature or a past activity mentioned in the channel's history
- **Personality system** — short character descriptors stored in `data/personalities.json`; switch at runtime, pin per-channel, persist across restarts
- **Conversation simulation** — simulate a debate between two personalities on any topic via `!simulate` / `/simulate`
- **Mini-games** — Tic-Tac-Toe (`!game`), Snake (`!snake`, button D-pad, score tracked), and a QUD-style ASCII dungeon (`!adventure`) — all panel-based
- **Game server management** — Minecraft (vanilla via SSH+Docker, modded local) and Satisfactory live panels; Satisfactory status pulled from the dedicated server HTTPS API (players, tech tier, play time); Valheim and Enshrouded start/stop commands; `!status` / `/status` shows all servers at a glance in one embed
- **Cog-based architecture** — each feature domain is a hot-reloadable `cogs/` module; most commands available as both `!prefix` and `/slash`

## Requirements

- Python 3.10+
- kitty terminal — required on Linux for **modded** Minecraft server start (launches the server process in a new terminal window); not needed for vanilla (SSH+Docker) or any other feature

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Setup

All configuration lives in a single **`.env`** file at the project root.

```env
# ─────────────────────────────────────────────
# Discord
# ─────────────────────────────────────────────

# Bot token from the Discord Developer Portal (Bot tab)
DISCORD_TOKEN=your_discord_bot_token

# Comma-separated channel IDs the bot listens in and responds to automatically.
# The bot always responds to direct @mentions regardless of this list.
CHANNEL_IDS=123456789,987654321


# ─────────────────────────────────────────────
# OpenAI
# ─────────────────────────────────────────────

OPENAI_API_KEY=your_openai_api_key

# Model used for chat completions
MODEL_CHAT=gpt-4o

# Max tokens for normal chat responses
MAX_TOKENS=500

# Response creativity (0.0–2.0). 1.5 is expressive and characterful; lower = more focused.
TEMPERATURE=1.5

# Image dimensions: 1024x1024 / 1536x1024 (landscape) / 1024x1536 (portrait)
IMAGE_SIZE=1024x1024

# Image quality: low / medium / high (higher = better quality and higher cost)
IMAGE_QUALITY=medium

# Max tokens for image analysis responses. Raise if descriptions are cut off.
ANALYZE_MAX_TOKENS=500

# Enable or disable emoji reaction responses (true/false)
REACTION_RESPONSES=true

# Python logging level for data/bot.log (DEBUG / INFO / WARNING / ERROR).
# Console always shows INFO+. Use DEBUG when hunting bugs.
LOG_LEVEL=WARNING


# ─────────────────────────────────────────────
# Chat History & RAG Memory
# ─────────────────────────────────────────────

# Recent Discord messages fetched directly per response (the immediate window).
HISTORYLENGTH=30

# Semantically relevant past messages retrieved from ChromaDB per response.
# These come from beyond the history window — older context only.
RAG_MESSAGE_CONTEXT=50

# Document chunks retrieved from ChromaDB per response (!learn content).
RAG_DOC_CONTEXT=5

# Days before a chat message is excluded from retrieval. Documents never expire.
MESSAGE_TTL_DAYS=30

# Cosine distance cutoff (0–2; lower = more similar). Results above this are dropped.
# Raise if relevant context is missed; lower if too much noise comes through.
DISTANCE_THRESHOLD=0.8

# Recency decay half-life in days for message retrieval scoring.
# A message this many days old must be twice as similar to survive the distance threshold.
# Keeps recent context competitive with older on-topic messages. Set to 0 to disable.
# Documents are never decayed.
RAG_DECAY_HALFLIFE_DAYS=14

# Optional hard token budget for the full LLM payload (estimated as chars÷4).
# If set, RAG messages are trimmed from the tail (lowest relevance) first, then docs.
# Leave unset for no cap. Give headroom — the estimate is approximate.
# MAX_CONTEXT_TOKENS=8000


# ─────────────────────────────────────────────
# User Profiles
# ─────────────────────────────────────────────

# Enable per-user fact extraction and profile injection (true/false).
# Profiles are stored in data/user_profiles.json (gitignored).
USER_PROFILE_EXTRACTION=true

# Max facts stored per user. Oldest facts are dropped when the cap is hit.
USER_PROFILE_MAX_FACTS=20

# Max facts injected into the system prompt per call. Most recent facts are preferred.
USER_PROFILE_INJECT_MAX=10

# Model used for fact extraction. Can be a cheaper/faster model — it's a simple task.
# Defaults to MODEL_CHAT if unset.
# USER_PROFILE_MODEL=gpt-4o-mini

# Max tokens for the extraction response.
USER_PROFILE_EXTRACT_TOKENS=200

# Max chars of user/bot message fed to the extraction prompt.
USER_PROFILE_MSG_CHARS=500


# ─────────────────────────────────────────────
# Auto-Summarization
# ─────────────────────────────────────────────

# Enable background conversation summarization (true/false).
SUMMARY_ENABLED=true

# How often (in hours) the summarizer scans all channels.
SUMMARY_INTERVAL_HOURS=24

# Min expiring messages needed to trigger summarization.
# Below this count, the run is skipped unless SUMMARY_FORCE_AFTER_DAYS has elapsed.
SUMMARY_MIN_NEW_MESSAGES=10

# Force summarization after this many days without one, regardless of message count.
# Prevents messages expiring without being captured on quiet days.
SUMMARY_FORCE_AFTER_DAYS=5

# Summarize messages this many days before their TTL expires. Buffer against data loss.
SUMMARY_DAYS_BEFORE_EXPIRY=5

# Model used for summarization. Defaults to MODEL_CHAT if unset.
# SUMMARY_MODEL=gpt-4o-mini

# Max tokens in the summary output.
SUMMARY_MAX_TOKENS=500

# Max chars of chat history fed to the summarizer per run. Caps cost on active channels.
SUMMARY_MAX_INPUT_CHARS=12000


# ─────────────────────────────────────────────
# Google Search
# ─────────────────────────────────────────────

# Google Custom Search API key — used by !image
GOOGLE_API_KEY=your_google_api_key

# Google Custom Search Engine ID — configure at programmablesearchengine.google.com
GOOGLE_CSE_ID=your_cse_id


# ─────────────────────────────────────────────
# Web Search (Tavily)
# ─────────────────────────────────────────────

# Tavily API key — powers the AI web search tool (bot searches automatically in conversation).
# Free tier available at tavily.com. Leave blank to disable.
TAVILY_API_KEY=tvly-your_tavily_key


# ─────────────────────────────────────────────
# Minecraft Servers
# ─────────────────────────────────────────────

MINECRAFT_VANILLA_SSH_HOST=192.168.0.x        # remote host — start via SSH+Docker
MINECRAFT_VANILLA_SSH_USER=admin             # optional SSH user
MINECRAFT_VANILLA_COMPOSE_DIR=/home/data     # path to docker-compose on remote host
MINECRAFT_VANILLA_RCON_HOST=192.168.0.x      # host for RCON status checks
MINECRAFT_VANILLA_RCON_PORT=25575
MINECRAFT_VANILLA_RCON_PASSWORD=your_rcon_password

MINECRAFT_MODDED_DIR=/home/user/minecraft/modded   # local path for kitty launch
MINECRAFT_MODDED_RCON_HOST=localhost
MINECRAFT_MODDED_RCON_PORT=25575
MINECRAFT_MODDED_RCON_PASSWORD=your_rcon_password


# ─────────────────────────────────────────────
# Satisfactory Server
# ─────────────────────────────────────────────

SATISFACTORY_SSH_HOST=192.168.0.x            # required — remote host for start/stop
SATISFACTORY_SSH_USER=admin                  # optional SSH user
SATISFACTORY_COMPOSE_DIR=/home/data          # path to docker-compose on remote host
# SATISFACTORY_API_HOST=                     # optional — defaults to SSH host
SATISFACTORY_API_PORT=7777                   # HTTPS API port (default: 7777)

# Which servers appear in !status / /status (comma-separated)
# Valid values: minecraft_vanilla, minecraft_modded, satisfactory
STATUS_SERVERS=minecraft_vanilla,minecraft_modded,satisfactory


# ─────────────────────────────────────────────
# Valheim & Enshrouded (Windows only)
# ─────────────────────────────────────────────

VALHEIM_SERVER_NAME=MyValheimServer
VALHEIM_WORLD_NAME=MyWorld
VALHEIM_PASSWORD=your_password
VALHEIM_PORT=2456
VALHEIM_STEAM_DIR=I:\SteamLibrary

ENSHROUDED_EXE=I:\SteamCMD\steamapps\common\enshrouded_server\enshrouded_server.exe


# ─────────────────────────────────────────────
# Personalities (legacy — migrated to data/personalities.json on first run)
# ─────────────────────────────────────────────

# These entries are read once on first start to populate data/personalities.json.
# After migration, personalities.json is the source of truth and these are ignored.
# Add/remove/change personalities at runtime via !new, !change, !list, /personality.
PERSONALITY=a sarcastic assistant named Soupy Dafoe obsessed with soup
PERSONALITY=an enthusiastic valley girl with a secret PhD in Astrophysics named Tiffany
ACTIVE_PERSONALITY=a sarcastic assistant named Soupy Dafoe obsessed with soup
```

## Running

```bash
source .venv/bin/activate
python main.py
```

## Commands

Most commands work as both `!prefix` and `/slash`. Exceptions are noted.

### Chat & Personality

| Prefix | Slash | Description |
|---|---|---|
| `!change [n]` | `/personality change [n]` | Switch to personality #n, or pick randomly |
| `!new <text>` | `/personality new <text>` | Add a new personality descriptor |
| `!list` | `/personality list` | List all personalities |
| `!pin [n]` | `/personality pin [n]` | Pin personality #n to this channel permanently |
| `!unpin` | `/personality unpin` | Remove the channel personality pin |
| — | `/personality remove <n>` | Remove personality at index n |
| `!simulate [p1] [p2] <topic>` | `/simulate` | Simulate a debate between two personalities |

### Memory (RAG)

| Prefix | Slash | Description |
|---|---|---|
| `!learn <text>` | `/learn` | Store text in memory |
| `!learn` + attachment | `/learn` + file | Store a file in memory (.txt, .py, .md, .pdf, .json, .csv, and more) |
| `!memory` | `/memory` | Show how many chunks are stored for this channel |
| `!summarize` | `/summarize` | TL;DR of recent conversation |
| `!cleardocs` | `/cleardocs` | Remove stored documents (keeps message history) |
| `!clearall` | — | Wipe all memory for this channel (requires Manage Messages) |

### Images

| Prefix | Slash | Description |
|---|---|---|
| `!generate <prompt>` | `/generate` | Generate an image with gpt-image-1 |
| `!transform <instructions>` | `/transform` | Transform an attached image |
| `!transform last <instructions>` | `/transform use_last:True` | Transform the most recent image in this channel |
| `!image <query>` | `/image` | Search Google Images and describe the result |
| *(natural language)* | — | Ask the bot to generate or transform in conversation |

### Games

| Prefix | Slash | Description |
|---|---|---|
| `!game X\|O` | `/game` | Play Tic-Tac-Toe (choose your symbol) |
| `!snake` | `/snake` | Play Snake (button D-pad, score tracked) |
| `!adventure` | `/adventure` | ASCII dungeon (QUD-style grid, 8-directional, items, win condition) |

### Game Servers

| Prefix | Slash | Description |
|---|---|---|
| `!status` | `/status` | Live status embed for all game servers |
| `!minecraft` | `/minecraft` | Open the Minecraft server panel |
| `!satisfactory` | `/satisfactory` | Open the Satisfactory server panel |
| `!start_valheim` | `/valheim start` | Start the Valheim dedicated server |
| `!stop_valheim` | `/valheim stop` | Stop the Valheim dedicated server |
| `!valheim_status` | `/valheim status` | Check Valheim server status |
| `!start_enshrouded` | `/enshrouded start` | Start the Enshrouded dedicated server |
| `!stop_enshrouded` | `/enshrouded stop` | Stop the Enshrouded dedicated server |

### Misc

| Prefix | Slash | Description |
|---|---|---|
| `!commands` / `!help` | `/commands` / `/help` | Show all bot commands with descriptions |
| `!sandwich` | `/sandwich` | Generate a random sandwich with an AI image |

## Architecture

```
main.py                       — bot init, shared state, load_extension calls, bot.run()
cogs/
  chat.py                     — on_message/on_reaction_add queue-based handler; RAG
                                integration; AI image/search/suggest tools; profile
                                injection and background extraction; summarizer start
  images.py                   — generate, transform, image commands
  personality.py              — prefix + slash personality commands
  games.py                    — game, snake, adventure commands
  servers.py                  — minecraft, valheim, enshrouded server commands
  fun.py                      — commands/help (formatted text list), simulate, sandwich
  rag.py                      — learn, memory, summarize, cleardocs, clearall
AIfunc/
  responses.py                — BASE_SYSTEM_PROMPT; generate_gpt_response (rag_context,
                                user_context, tools, auto_resolve), analyze_image,
                                generate_image, transform_image
  simulate.py                 — ConversationSimulator
chatbotfunc/
  logger.py                   — setup_logging(): RotatingFileHandler → data/bot.log
  utils.py                    — fetch_message_history, async_chat_completion,
                                split_message, format_error_message, encode_discord_image,
                                SUPPORTED_DOC_EXTENSIONS
  personalitymanager.py       — PersonalityManager: data/personalities.json store;
                                auto-migrates from .env on first run; per-channel pin
                                cache in data/channel_personalities.json
  profiles.py                 — get_user_context(), extract_and_update(); reads/writes
                                data/user_profiles.json (gitignored)
  summarizer.py               — summarizer_loop(), summarize_channel(); skip/force logic;
                                state in data/summarizer_state.json (gitignored)
ragfunc/
  memory.py                   — ChannelMemory (ChromaDB singleton client); store_message
                                (context_snippet support), store_document, retrieve
                                (decay + before_ts filter), get_expiring, delete_by_ids,
                                clear methods; list_channel_ids(); async helpers
gamefunc/
  adventure.py / adventure_panel.py  — 55×23 ASCII dungeon, viewport renderer, D-pad UI
  snake_panel.py              — Snake game, D-pad buttons, score tracking
  minecraft.py / minecraft_panel.py  — thread-safe RCON; vanilla starts via SSH+Docker,
                                modded via local kitty; live status panel
  satisfactory.py             — SSH+Docker start/stop; HTTPS API state (players, tier,
                                play time, tick rate); token caching with auto-refresh
  satisfactory_panel.py       — Satisfactory management panel (Start/Stop/Restart/Refresh)
  status_panel.py             — read-only all-servers status embed; parallel queries;
                                configurable via STATUS_SERVERS env var
  valheim.py                  — ValheimServer, EnshroudedServer (Windows-only)
  tictactoe.py                — Tic-Tac-Toe logic
funfunc/
  image_search.py             — Google Custom Search wrapper
  web_search.py               — Tavily web search (AI google_search tool)
  sandwich.py                 — random sandwich generator
data/                         — runtime artifacts (all gitignored except personalities.json)
  chroma/                     — ChromaDB persistent vector store
  personalities.json          — personality descriptor list + active selection
  channel_personalities.json  — per-channel personality pin map
  user_profiles.json          — per-user extracted fact profiles (gitignored)
  summarizer_state.json       — last-summary timestamps per channel (gitignored)
  bot.log                     — rotating log file
```

## RAG Memory System

Every qualifying message the bot processes is stored in a per-channel ChromaDB collection (`data/chroma/`). Before generating any response, a semantic similarity search retrieves the most relevant past messages and document chunks, which are injected into the system prompt. This gives the bot long-term memory without bloating the token window with raw history.

**Context assembled per response:**
1. `HISTORYLENGTH` (default: 30) messages fetched directly from Discord — the immediate conversation window
2. Up to `RAG_MESSAGE_CONTEXT` (default: 50) semantically relevant *older* messages from ChromaDB — long-term memory, restricted to entries older than the history window so nothing is sent twice
3. Up to `RAG_DOC_CONTEXT` (default: 5) relevant document chunks from any `!learn` files

**Recency decay:** retrieved messages are scored with an exponential decay multiplier based on age. A message `RAG_DECAY_HALFLIFE_DAYS` (default: 14) old needs to be twice as similar to the current query to score the same as a new message. This keeps recent context competitive against older on-topic messages. Documents are never decayed.

**Context threading:** each stored message includes a `context_snippet` of the preceding exchange (user messages carry the last bot reply; bot replies carry the user prompt). Retrieved entries display this snippet as `[re: ...]` in the injected context, so the model understands what was being discussed when each memory was created rather than seeing it as an isolated fragment.

**Quality filter:** user messages are checked before storage — messages under 8 chars, pure emoji/URL content, and known filler phrases are discarded. Bot replies under 40 chars are also skipped. Bot responses and image analysis results that pass the threshold are always stored.

**Deduplication:** entries use Discord message IDs as ChromaDB document IDs — re-processing the same message never creates duplicates.

**Image analysis:** when you share an image in an allowed channel, the bot describes it in character and stores the description in RAG so it can reference past images in future conversations.

**File auto-storage:** dropping a supported file in an allowed channel stores it in RAG automatically. Supported types: `.txt .py .md .js .ts .jsx .tsx .json .csv .yaml .yml .html .css .sh .toml .ini .cfg .pdf`

PDFs are text-extracted via `pypdf`. Scanned/image-only PDFs won't have usable text.

**Auto-summarization:** a background task runs every `SUMMARY_INTERVAL_HOURS` (default: 24) and scans all channels. When messages are approaching their TTL expiry, they are condensed into a permanent summary document and then deleted. Skip/force logic: skip if fewer than `SUMMARY_MIN_NEW_MESSAGES` are expiring and a summary ran within `SUMMARY_FORCE_AFTER_DAYS` days — after that window, summarize regardless so nothing expires uncaptured. This makes effective memory infinite while keeping the RAG index clean.

## User Profiles

After every real text exchange, a lightweight background LLM call extracts new facts about the user from the conversation (preferences, games, habits, running jokes, anything distinctive) and merges them into `data/user_profiles.json`. On the next message from that user, the profile is injected into the system prompt as a `USER PROFILE:` section before RAG context, so the model knows who it's talking to without relying on retrieval.

Profiles are per-user (keyed by Discord user ID) and persist indefinitely. The `USER_PROFILE_MAX_FACTS` cap (default: 20) keeps profiles from bloating — the oldest facts are dropped when it's hit, keeping the most recently learned information. Gitignored; never committed.

## Personality System

`BASE_SYSTEM_PROMPT` in `AIfunc/responses.py` defines platform-level rules applied to every personality: Discord context, no hollow filler openers, code block formatting, RAG context handling, history handling, stay-in-character, and uncertainty behaviour.

Personalities are stored in `data/personalities.json` as a list of plain text descriptors. On first run, the bot auto-migrates any `PERSONALITY=` entries from `.env` into this file so existing personalities are preserved. After migration, `.env` entries are ignored.

Each descriptor is a short character description injected at the `{personality}` slot in `BASE_SYSTEM_PROMPT`. Keep them short — the base prompt handles all boilerplate:
- `a sarcastic, reluctant assistant named Soupy Dafoe preoccupied with soup`
- `Professor Hubert J. Farnsworth from Futurama — exclamatory, brilliantly absent-minded`
- `a DnD-style Sorceress who must roll a dice and announce the result before any action`

Use `!pin [n]` / `/personality pin [n]` to lock a specific personality to a channel. Pins are stored in `data/channel_personalities.json` and survive restarts. Remove with `!unpin` / `/personality unpin`.

## Known Limitations

- **Valheim / Enshrouded** commands are Windows-only (use `.bat` files and `CREATE_NEW_CONSOLE`). They will fail on Linux.
- **Image transform state** — `!transform last` and AI-triggered transforms require at least one `!generate` or `!transform` in the current session. Image bytes live in memory and are lost on restart.
- **Scanned PDFs** — `!learn` and file auto-storage extract text via `pypdf`. Image-only/scanned PDFs produce no usable text.
- **Token estimate** — `MAX_CONTEXT_TOKENS` trimming uses a chars÷4 approximation. Give yourself headroom when setting the cap.
- **Profile extraction latency** — user profiles are updated in the background after each response. A fact mentioned in message N is available starting from message N+1, not immediately.
- **Summarizer first run** — the background summarizer starts its first scan after `SUMMARY_INTERVAL_HOURS`, not immediately on startup.
- **RAG memory is per-channel** — each Discord channel has its own isolated collection. `!clearall` only affects the current channel.
