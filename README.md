# Discord Bot

A personal Discord bot with GPT chat, image generation and transformation, voice TTS, game server management, and in-channel mini-games.

## Features

- **GPT chat** — responds in allowed channels using a configurable personality/system prompt
- **Image generation** — gpt-image-1 image generation via `!generate`
- **Image transformation** — native image editing via `!transform` (uses `gpt-image-1` images.edit API directly)
- **Image analysis** — describe attached images in chat, or search and describe via `!image`
- **Personality system** — multiple switchable system prompts managed at runtime
- **Conversation simulation** — two bot personalities argue a topic via `!simulate`
- **Mini-games** — Tic-Tac-Toe (`!game`) and Snake (`!snake`) playable in Discord
- **Game server management** — start/stop/restart Minecraft (vanilla & modded), Valheim, and Enshrouded servers

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
PERSONALITY=You are a helpful assistant.
CHANNEL_IDS=123456789,987654321
HISTORYLENGTH=30
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
VALHEIM_STEAM_DIR=I:\SteamLibrary
ENSHROUDED_EXE=I:\SteamCMD\steamapps\common\enshrouded_server\enshrouded_server.exe
```

**`personalities.env`** — one personality per line:

```env
PERSONALITY=You are a pirate.
PERSONALITY=You are a sarcastic assistant.
```

This file is managed at runtime by `!new`, `!list`, and `/personality` slash commands.

## Running

```bash
source .venv/bin/activate
python main.py
```

## Commands

### Chat & Personality

| Command | Description |
|---|---|
| `!change [n]` | Switch to personality #n, or pick randomly if no number given |
| `!new <text>` | Add a new personality |
| `!list` | List all available personalities as a file |
| `/personality change [n]` | Slash command equivalent of `!change` (also saves to `.env`) |
| `/personality new <text>` | Slash command equivalent of `!new` |
| `/personality list` | Slash command equivalent of `!list` |
| `/personality remove <n>` | Remove personality at index n |

### Images

| Command | Description |
|---|---|
| `!generate <prompt>` | Generate an image with gpt-image-1 |
| `!transform <instructions>` | Transform an attached image using gpt-image-1 native editing |
| `!transform last <instructions>` | Transform the most recently generated image |
| `!image <query>` | Search Google Images and describe the result |

### Games

| Command | Description |
|---|---|
| `!game X\|O` | Play Tic-Tac-Toe (choose your symbol) |
| `!snake` | Play Snake (w/a/s/d to move) |

### Game Servers

| Command | Description |
|---|---|
| `!minecraft` | Open the Minecraft server panel (start/stop/restart/players buttons) |
| `!start_valheim` | Start the Valheim dedicated server |
| `!stop_valheim` | Stop the Valheim dedicated server |
| `!valheim_status` | Check if Valheim server process is running |
| `!start_enshrouded` | Start the Enshrouded dedicated server |
| `!stop_enshrouded` | Stop the Enshrouded dedicated server |

### Misc

| Command | Description |
|---|---|
| `!simulate [p1] [p2] <topic>` | Simulate a conversation between two personalities on a topic |
| `!prompt <topic>` | Generate a Google search URL for a topic via GPT |
| `!sandwich` | Generate a random sandwich |

## Architecture

```
main.py                     — entry point; all Discord event handlers and bot commands
AIfunc/
  responses.py              — OpenAI wrappers: generate_gpt_response, analyze_image,
                              generate_image, transform_image
  simulate.py               — ConversationSimulator
chatbotfunc/
  utils.py                  — fetch_message_history, async_chat_completion
  personalitymanager.py     — PersonalityManager (reads/writes personalities.env)
gamefunc/
  minecraft.py              — MinecraftServer (env-based config, async RCON)
  minecraft_panel.py        — MinecraftPanel Discord UI (buttons, live status)
  valheim.py                — ValheimServer, EnshroudedServer (Windows batch/exe)
  tictactoe.py              — play_tic_tac_toe
  snake.py                  — SnakeGame
funfunc/
  image_search.py           — Google Custom Search API wrapper
  prompt.py                 — GPTSearchPrompt
  sandwich.py               — random sandwich generator
```

## Known Limitations

- **Valheim / Enshrouded commands** are Windows-only (use `.bat` files and `CREATE_NEW_CONSOLE`). They will fail on Linux.
- **`!variation`** is currently broken — the OpenAI variations endpoint does not support gpt-image-1.
- **`!transform last`** requires at least one `!generate` call in the current session (bytes are not persisted across restarts).
