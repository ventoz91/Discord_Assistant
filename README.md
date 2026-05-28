# Discord Bot

A personal Discord bot with GPT chat, image generation and transformation, game server management, in-channel mini-games, and persistent RAG memory.

## Features

- **GPT chat** — responds in allowed channels using a configurable personality/system prompt; always responds to direct @mentions
- **RAG memory** — per-channel persistent memory backed by ChromaDB; stores chat history and uploaded documents, retrieves semantically relevant context on every response
- **Image generation** — gpt-image-1 image generation via `!generate` / `/generate`
- **Image transformation** — native image editing via `!transform` / `/transform`
- **Image analysis** — describe attached images in chat, or search and describe via `!image` / `/image`
- **Personality system** — short character descriptors injected into a shared base system prompt; switchable at runtime
- **Conversation simulation** — two bot personalities argue a topic via `!simulate` / `/simulate`
- **Mini-games** — Tic-Tac-Toe (`!game` / `/game`) and Snake (`!snake` / `/snake`) playable in Discord
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

Two env files are required at the project root.

**`.env`**

```env
DISCORD_TOKEN=your_discord_bot_token
OPENAI_API_KEY=your_openai_api_key
MODEL_CHAT=gpt-5.4
PERSONALITY=a short character descriptor e.g. "a sarcastic assistant named Soupy Dafoe obsessed with soup"
CHANNEL_IDS=123456789,987654321
HISTORYLENGTH=30
RAG_MESSAGE_CONTEXT=50
MAX_TOKENS=500

# Minecraft
MINECRAFT_VANILLA_DIR=/home/trevor/Documents/Vanilla_Server
MINECRAFT_VANILLA_RCON_HOST=localhost
MINECRAFT_VANILLA_RCON_PORT=25575
MINECRAFT_VANILLA_RCON_PASSWORD=your_rcon_password
MINECRAFT_MODDED_DIR=/home/trevor/Documents/AlexServer
MINECRAFT_MODDED_RCON_HOST=localhost
MINECRAFT_MODDED_RCON_PORT=25575
MINECRAFT_MODDED_RCON_PASSWORD=your_rcon_password

# Google Image Search
GOOGLE_API_KEY=your_google_api_key
GOOGLE_CSE_ID=your_cse_id

# Valheim / Enshrouded (Windows only)
VALHEIM_SERVER_NAME=MyValheimServer
VALHEIM_WORLD_NAME=MyWorld
VALHEIM_PASSWORD=your_password
VALHEIM_PORT=2456
VALHEIM_STEAM_DIR=I:\SteamLibrary
ENSHROUDED_EXE=I:\SteamCMD\steamapps\common\enshrouded_server\enshrouded_server.exe
```

**`personalities.env`** — one short personality descriptor per line:

```env
PERSONALITY=a sarcastic assistant named Soupy Dafoe obsessed with soup
PERSONALITY=an enthusiastic valley girl with a secret PhD in Astrophysics named Tiffany
```

Each entry is a short character description injected into `BASE_SYSTEM_PROMPT` in `AIfunc/responses.py`. The base prompt handles all platform rules (Discord context, concise responses, code formatting, history handling) so personalities only need to describe the character. Managed at runtime via `!new`, `!list`, and `/personality` slash commands.

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
| — | `/personality change [n]` | Switch personality (also saves to `.env`) |
| — | `/personality new <text>` | Add a new personality |
| — | `/personality list` | List personalities |
| — | `/personality remove <n>` | Remove personality at index n |

### Memory (RAG)

| Prefix | Slash | Description |
|---|---|---|
| `!learn <text>` | `/learn` | Store text directly in memory |
| `!learn` + attachment | `/learn` + file | Store a file in memory (.txt, .py, .md, .pdf, .json, .csv, and more) |
| `!memory` | `/memory` | Show how many chunks are stored for this channel |
| `!cleardocs` | `/cleardocs` | Remove all stored documents (keeps message history) |
| `!clearall` | — | Wipe all memory for this channel (requires Manage Messages) |

### Images

| Prefix | Slash | Description |
|---|---|---|
| `!generate <prompt>` | `/generate <prompt>` | Generate an image with gpt-image-1 |
| `!transform <instructions>` | `/transform` | Transform an attached image |
| `!transform last <instructions>` | `/transform use_last:True` | Transform the last generated image |
| `!image <query>` | `/image <query>` | Search Google Images and describe the result |


### Games

| Prefix | Slash | Description |
|---|---|---|
| `!game X\|O` | `/game` | Play Tic-Tac-Toe (choose your symbol) |
| `!snake` | `/snake` | Play Snake (w/a/s/d to move) |

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
  chat.py                   — on_message, on_reaction_add, on_ready (GPT chat handler + RAG integration)
  images.py                 — generate, transform, image, variation commands
  personality.py            — prefix + slash personality commands
  games.py                  — game (Tic-Tac-Toe), snake commands
  servers.py                — minecraft, valheim, enshrouded server commands
  fun.py                    — prompt, simulate, sandwich commands
  rag.py                    — learn, memory, cleardocs, clearall commands
AIfunc/
  responses.py              — BASE_SYSTEM_PROMPT constant; OpenAI wrappers:
                              generate_gpt_response (accepts rag_context),
                              analyze_image, generate_image, transform_image
  simulate.py               — ConversationSimulator
chatbotfunc/
  utils.py                  — fetch_message_history, async_chat_completion,
                              split_message, format_error_message, encode_discord_image
  personalitymanager.py     — PersonalityManager (reads/writes personalities.env)
gamefunc/
  minecraft.py              — MinecraftServer (thread-safe async RCON, no signal module)
  minecraft_panel.py        — MinecraftPanel Discord UI (buttons, live status)
  valheim.py                — ValheimServer, EnshroudedServer (Windows batch/exe)
  tictactoe.py              — play_tic_tac_toe
  snake.py                  — SnakeGame
ragfunc/
  memory.py                 — ChannelMemory (ChromaDB wrapper); store_message, store_document,
                              retrieve, clear methods; async helpers
funfunc/
  image_search.py           — Google Custom Search API wrapper
  prompt.py                 — GPTSearchPrompt
  sandwich.py               — random sandwich generator
data/
  chroma/                   — ChromaDB persistent vector store (auto-created, gitignored)
```

## RAG Memory System

Every message the bot processes is stored in a per-channel ChromaDB collection on disk (`data/chroma/`). Before generating any response, the bot runs a semantic similarity search and injects the most relevant past messages and document chunks into the system prompt. This gives the bot long-term memory without bloating the token window with raw history.

**How context works per response:**
- Last `HISTORYLENGTH` messages (default: 30) fetched directly from Discord — the immediate conversation window
- Top `RAG_MESSAGE_CONTEXT` semantically relevant past messages retrieved from ChromaDB (default: 50) — long-term memory
- Top 5 relevant document chunks from any stored files — knowledge base

**Supported file types for `!learn`:**
`.txt` `.py` `.md` `.js` `.ts` `.jsx` `.tsx` `.json` `.csv` `.yaml` `.yml` `.html` `.css` `.sh` `.toml` `.ini` `.cfg` `.pdf`

PDFs are text-extracted via `pypdf`. Scanned/image-only PDFs won't have extractable text.

**Memory is per-channel** — each Discord channel has its own isolated collection. `!clearall` only affects the current channel.

## Personality System

`BASE_SYSTEM_PROMPT` in `AIfunc/responses.py` defines platform-level rules that apply to every personality:
- Discord context (concise, conversational responses)
- Code block formatting
- History handling (focus on recent, use history as context)
- Stay in character directive

Each entry in `personalities.env` is a short character descriptor injected at the `{personality}` slot. Examples:
- `a sarcastic, reluctant assistant named Soupy Dafoe preoccupied with soup`
- `Professor Hubert J. Farnsworth from Futurama — exclamatory, brilliantly absent-minded`
- `a DnD-style Sorceress who must roll a dice and announce the result before any action`

## Known Limitations

- **Valheim / Enshrouded commands** are Windows-only (use `.bat` files and `CREATE_NEW_CONSOLE`). They will fail on Linux.
- **`!transform last`** requires at least one `!generate` call in the current session (bytes are not persisted across restarts).
- **Scanned PDFs** — `!learn` can only extract text from text-based PDFs. Image-only scans won't work.
- **Re-uploading files** — if a file was stored before the chunk size was increased to 3000 chars, re-upload it with `!learn` to get better chunking.
