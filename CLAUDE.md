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
- `PERSONALITY` — Active system prompt for the bot's behavior
- `CHANNEL_IDS` — Comma-separated Discord channel IDs the bot listens to
- `HISTORYLENGTH` — Number of messages to fetch as context (default: 30)
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
- `VALHEIM_STEAM_DIR` — Path to Steam directory (Windows)
- `ENSHROUDED_EXE` — Full path to enshrouded_server.exe (Windows)

**`personalities.env`** — personality definitions, one per line in the format `PERSONALITY=<prompt text>`. Managed at runtime via `PersonalityManager`.

## Architecture Overview

`main.py` is the entry point and contains all Discord event handlers and bot commands. Everything else is organized into modules:

### Module Layout

- **`AIfunc/responses.py`** — Core OpenAI wrappers: `generate_gpt_response()`, `analyze_image()`, `generate_image()`, `transform_image()`.
- **`AIfunc/simulate.py`** — `ConversationSimulator`: simulates a back-and-forth conversation between two bot personalities on a given topic.
- **`chatbotfunc/utils.py`** — `fetch_message_history()` (fetches Discord channel history as OpenAI message format) and `async_chat_completion()` (wraps `openai.chat.completions.create` in a thread).
- **`chatbotfunc/personalitymanager.py`** — `PersonalityManager`: reads/writes/manages personalities from `personalities.env`. Personalities are system prompts stored one per line.
- **`gamefunc/`** — Minecraft server management (`minecraft.py`), Minecraft button panel (`minecraft_panel.py`), Valheim/Enshrouded server management (`valheim.py`), Tic-Tac-Toe (`tictactoe.py`), Snake (`snake.py`).
- **`funfunc/`** — Image search (`image_search.py`), Google search prompt generation (`prompt.py`), random sandwich generator (`sandwich.py`).

### Message Flow

`on_message` in `main.py` is the main handler. It:
1. Ignores bot's own messages and `!`-prefixed commands (routes those to `bot.process_commands`)
2. Skips channels with active games
3. Processes image attachments via `analyze_image()` if present
4. Processes `.txt` file attachments by storing content in `channel_file_contents[channel_id]`
5. Calls `should_bot_respond_to_message()` to check if the channel is in `CHANNEL_IDS` and no human @mentions are present
6. Fetches history via `fetch_message_history()`, appends the user message, calls `generate_gpt_response()`, and sends via `split_message()`
7. Sends the response via `split_message()`

### Command Prefix vs Slash Commands

The bot uses both `!` prefix commands (`@bot.command()`) and slash commands (`@percmd.command()` via `bot.create_group("personality")`). The personality slash commands under `/personality` duplicate some `!` prefix commands — both coexist.

### Key Globals in `main.py`

- `chatgpt_behaviour` — Active system prompt string; changed at runtime by `!change` / `/personality change`
- `active_games` — `dict[channel_id, bool]` to prevent message handling during in-channel games
- `channel_file_contents` — `dict[channel_id, str]` stores uploaded text file content injected into chat history
- `last_generated_image_bytes` — Raw PNG bytes of the last `!generate` result; used by `!transform last`

### Bot Commands Reference

| Command | Description |
|---|---|
| `!generate <prompt>` | Generate an image via gpt-image-1 |
| `!transform <instructions>` | Transform attached image using gpt-image-1 native editing |
| `!transform last <instructions>` | Transform the most recently generated image |
| `!image <query>` | Search and display an image with AI description |
| `!change [n]` | Switch to personality #n or random |
| `!new <personality>` | Add a new personality |
| `!list` | List available personalities |
| `!simulate [p1] [p2] <topic>` | Simulate conversation between two personalities |
| `!game X\|O` | Play Tic-Tac-Toe |
| `!snake` | Play Snake |
| `!minecraft` | Open the Minecraft server management panel |
| `!start_valheim` / `!stop_valheim` | Manage Valheim server |
| `!prompt <topic>` | Generate a Google search URL for a topic |
| `!sandwich` | Generate a random sandwich |
