# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
# Activate the virtual environment first
source .venv/bin/activate

# Run the Discord bot
python main.py

# Run the Flask voice upload server (separate process)
python flaskserv.py
```

## Environment Configuration

Two env files are required at the project root:

**`.env`** — core settings:
- `DISCORD_TOKEN` — Discord bot token
- `OPENAI_API_KEY` — OpenAI API key
- `MODEL_CHAT` — OpenAI model (e.g. `gpt-5.4`)
- `PERSONALITY` — Active system prompt for the bot's behavior
- `TRANSFORM` — System prompt used for image transformation
- `CHANNEL_IDS` — Comma-separated Discord channel IDs the bot listens to
- `HISTORYLENGTH` — Number of messages to fetch as context (default: 30)
- `MAX_TOKENS` — Max completion tokens for responses

**`personalities.env`** — personality definitions, one per line in the format `PERSONALITY=<prompt text>`. Managed at runtime via `PersonalityManager`.

## Architecture Overview

`main.py` is the entry point and contains all Discord event handlers and bot commands. Everything else is organized into modules:

### Module Layout

- **`AIfunc/responses.py`** — Core OpenAI wrappers: `generate_gpt_response()`, `analyze_image()`, `analyze_img()`, `generate_image()`. Also contains `start_monitoring()` which watches `./recordings/` for new audio files via watchdog and triggers TTS responses in voice channels.
- **`AIfunc/simulate.py`** — `ConversationSimulator`: simulates a back-and-forth conversation between two bot personalities on a given topic.
- **`chatbotfunc/utils.py`** — `fetch_message_history()` (fetches Discord channel history as OpenAI message format) and `async_chat_completion()` (wraps `openai.chat.completions.create` in a thread).
- **`chatbotfunc/personalitymanager.py`** — `PersonalityManager`: reads/writes/manages personalities from `personalities.env`. Personalities are system prompts stored one per line.
- **`gamefunc/`** — Minecraft server management (`minecraft.py`), Valheim/Enshrouded server management (`valheim.py`), Tic-Tac-Toe (`tictactoe.py`), Snake (`snake.py`).
- **`funfunc/`** — Image search (`image_search.py`), Google search prompt generation (`prompt.py`), random sandwich generator (`sandwich.py`).
- **`flaskserv.py`** — Standalone Flask server that accepts audio file uploads to `./recordings/`, converts them to WAV via ffmpeg, and the watchdog in `responses.py` picks them up for voice TTS processing.
- **`templates/index.html`** — Frontend for the Flask audio upload server.

### Message Flow

`on_message` in `main.py` is the main handler. It:
1. Ignores bot's own messages and `!`-prefixed commands (routes those to `bot.process_commands`)
2. Skips channels with active games
3. Processes image attachments via `analyze_image()` if present
4. Processes `.txt` file attachments by storing content in `channel_file_contents[channel_id]`
5. Calls `should_bot_respond_to_message()` to check if the channel is in `CHANNEL_IDS` and no human @mentions are present
6. Fetches history via `fetch_message_history()`, appends the user message, calls `generate_gpt_response()`, and sends via `split_message()`
7. If a voice client is connected, also generates a TTS response via gTTS and plays it

### Command Prefix vs Slash Commands

The bot uses both `!` prefix commands (`@bot.command()`) and slash commands (`@percmd.command()` via `bot.create_group("personality")`). The personality slash commands under `/personality` duplicate some `!` prefix commands — both coexist.

### Key Globals in `main.py`

- `chatgpt_behaviour` — Active system prompt string; changed at runtime by `!change` / `/personality change`
- `active_games` — `dict[channel_id, bool]` to prevent message handling during in-channel games
- `channel_file_contents` — `dict[channel_id, str]` stores uploaded text file content injected into chat history
- `last_generated_image_url` — Tracks the last DALL-E generated image for `!transform` and `!variation`

### Voice/Audio Pipeline

Audio flows through two paths:
1. **In-channel TTS**: When the bot is in a voice channel, `on_message` generates a GPT response and speaks it via gTTS + FFmpegPCMAudio
2. **Recording upload**: `flaskserv.py` receives audio uploads → saves to `./recordings/` → watchdog in `start_monitoring()` detects new files → Azure Speech SDK transcribes → GPT responds → TTS plays in voice channel

### Bot Commands Reference

| Command | Description |
|---|---|
| `!generate <prompt>` | Generate an image via DALL-E |
| `!transform [last] <instructions>` | Transform attached image or last generated |
| `!image <query>` | Search and display an image with AI description |
| `!change [n]` | Switch to personality #n or random |
| `!new <personality>` | Add a new personality |
| `!list` | List available personalities |
| `!simulate [p1] [p2] <topic>` | Simulate conversation between two personalities |
| `!game X\|O` | Play Tic-Tac-Toe |
| `!snake` | Play Snake |
| `!start/stop/restart/players <type>` | Manage Minecraft servers |
| `!start_valheim` / `!stop_valheim` | Manage Valheim server |
| `!join` / `!leave` | Join/leave voice channel |
| `!prompt <topic>` | Generate a Google search URL for a topic |
| `!sandwich` | Generate a random sandwich |
