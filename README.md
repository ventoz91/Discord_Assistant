# Discord Bot

A personal Discord bot with GPT chat, persistent long-term memory, per-user profiles, image generation and transformation, reminders, a daily in-character channel recap, game server management, and in-channel mini-games.

## Features

- **GPT chat** — responds in configured channels and always to @mentions; in-character responses shaped by the active personality; per-channel message queue prevents concurrent processing races
- **Agentic tool loop** — the model can chain tool calls (search → refine → search) across up to `MAX_AGENT_TURNS` follow-up rounds before it has to answer; web search and activity suggestions are auto-resolved internally, image tools are handled by the cog
- **Long-term RAG memory** — per-channel ChromaDB-backed memory; stores chat history and uploaded documents; semantically relevant context injected on every response; recency decay ensures old messages don't crowd out recent ones; RAG messages and direct history are kept deduplicated so nothing is sent to the model twice
- **User profiles** — after each exchange, a background LLM call extracts facts about the user (preferences, hobbies, games played, etc.) and stores them in `data/user_profiles.json`; the profile is injected into the system prompt so the bot genuinely knows who it's talking to; `!whoami` / `/whoami` shows the stored facts, `!forget` / `/forget` deletes one or all of them
- **Debates & running jokes** — a background scanner periodically reviews recent channel history and tracks ongoing threads (arguments, running bits, unresolved questions); the bot brings one up naturally if it genuinely fits, with a cooldown so it doesn't repeat itself
- **Auto-summarization** — a background task periodically condenses expiring messages into permanent summary documents before they vanish; effective memory is infinite; summaries survive indefinitely while raw message noise is cleaned up
- **The Morning Paper** — an optional daily in-character recap posted to configured channels, summarizing the last 24 hours; skips quiet days
- **`!missed` / `/missed`** — catch-up summary of everything that happened in a channel since you last spoke there
- **Reminders** — `!remind <duration> <text>` (compounds like `1h30m`) delivers an in-character reminder later; `!reminders` lists pending ones, `!unremind <id>` cancels one
- **Image generation** — gpt-image models (switchable with `/model`) via `!generate` / `/generate`, or naturally in conversation ("draw me a crab")
- **Image transformation** — AI image editing via `!transform` / `/transform`, or naturally in conversation ("make it blue"); transforms chain — each uses the previous result, not the original
- **Image/video/sticker analysis** — describes images, short videos (sampled across `VIDEO_FRAMES` frames), stickers, and lone custom emoji shared in chat; search and describe via `!image` / `/image`
- **Web search** — Tavily-backed tool calling; the bot searches automatically when a question needs current info and incorporates results into its in-character response
- **Suggest activity** — when asked what to do, the bot randomly recommends a bot feature or a past activity mentioned in the channel's history
- **Personality system** — short character descriptors stored in `data/personalities.json`; switch at runtime, pin per-channel, persist across restarts
- **Conversation simulation** — simulate a debate between two personalities on any topic via `!simulate` / `/simulate`
- **Mini-games** — Tic-Tac-Toe (`!game`), Snake (`!snake`, button D-pad, score tracked), and a QUD-style ASCII dungeon (`!adventure`) — all panel-based
- **Game server management** — Minecraft (vanilla + creative via SSH+Docker behind a Velocity proxy; modded as a systemd service on a desktop PC), Satisfactory, Palworld, RuneScape: Dragonwilds, and the EmuCoach WoW repack (Windows VM over SSH) all have start/stop/status; SSH access uses a dedicated, command-restricted key (see [Scoped SSH access](#scoped-ssh-access)); `!status` / `/status` shows all configured servers at a glance in one embed; background watchers announce Minecraft/Satisfactory events to configured channels
- **Web admin panel** (`webpanel/`) — browser dashboard for every server above: live status, start/stop, and pull-and-redeploy, plus a "Deploy new server" flow that spins up additional game servers from templates (or a custom Docker image) on a configured host. Runs inside the same process as the bot (see [Running](#running)) so it shares `gamefunc/` control code and can post panel actions to the same Discord channels the bot's own event watchers use. Session-login protected with a brute-force lockout — see [Web Panel](#web-panel) below
- **Model switching** — `/model` shows the current chat and image models with a dropdown for each; anyone can switch between curated, verified models and the change applies bot-wide immediately
- **Cost tracking** — every OpenAI call's token usage is recorded per feature and model; `/usage` shows estimated spend for today, 7 and 30 days
- **Bot self-restart** — an owner (`BOT_OWNER_IDS`) can ask the bot in chat to restart itself; it re-execs in place, picking up any code changes since the last start
- **Cog-based architecture** — each feature domain is a hot-reloadable `cogs/` module; most commands available as both `!prefix` and `/slash`

## Requirements

- Python 3.10+

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

# Comma-separated Discord user IDs allowed to ask the bot to restart itself in chat.
BOT_OWNER_IDS=123456789


# ─────────────────────────────────────────────
# OpenAI
# ─────────────────────────────────────────────

OPENAI_API_KEY=your_openai_api_key

# Model used for chat completions
MODEL_CHAT=gpt-6-sol

# Image model for generate/transform (default: gpt-image-1). /model in Discord can
# override this and MODEL_CHAT at runtime (stored in data/model_settings.json);
# picking "Default" there falls back to these .env values.
IMAGE_MODEL=gpt-image-1

# Days of per-feature usage/cost history kept in data/usage.json for /usage.
USAGE_RETENTION_DAYS=90

# Reasoning effort sent on every chat call (default: none). GPT-6 models reject
# function tools on Chat Completions unless this is "none". Set to "off" to omit
# the param entirely for non-reasoning models like gpt-4o.
REASONING_EFFORT=none

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

# Frames sampled evenly across a shared video for vision analysis. 1 = first-frame only (cheapest).
VIDEO_FRAMES=5

# Enable or disable emoji reaction responses (true/false)
REACTION_RESPONSES=true

# Python logging level for data/bot.log (DEBUG / INFO / WARNING / ERROR).
# Console always shows INFO+. Use DEBUG when hunting bugs.
LOG_LEVEL=WARNING

# Max follow-up rounds in the agentic tool loop — how many extra LLM calls the model
# can chain (search → refine → search) before it's forced to answer.
MAX_AGENT_TURNS=4


# ─────────────────────────────────────────────
# Chat History & RAG Memory
# ─────────────────────────────────────────────

# Recent Discord messages fetched directly per response (the immediate window).
HISTORYLENGTH=30

# Semantically relevant past messages retrieved from ChromaDB per response.
# These come from beyond the history window — older context only. The distance
# threshold drops most candidates anyway (median 0, p90 ~14 in practice), so this
# mostly caps the outliers.
RAG_MESSAGE_CONTEXT=20

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
# Leave unset for no cap. Give headroom — the estimate is approximate. Recent
# chat history is never trimmed, only RAG context.
MAX_CONTEXT_TOKENS=6000


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
# USER_PROFILE_MODEL=gpt-6-luna

# Max tokens for the extraction response.
USER_PROFILE_EXTRACT_TOKENS=200

# Max chars of user/bot message fed to the extraction prompt.
USER_PROFILE_MSG_CHARS=500


# ─────────────────────────────────────────────
# Debates & Running Jokes
# ─────────────────────────────────────────────

# Enable the background debate/running-joke tracker (true/false).
DEBATE_TRACKING=true

# How often (in hours) the scanner reviews recent channel history.
DEBATE_SCAN_INTERVAL_HOURS=12

# Minimum new messages since the last scan before bothering to run extraction.
DEBATE_SCAN_MIN_MESSAGES=20

# Max chars of recent chat fed to the extraction LLM call per scan.
DEBATE_SCAN_MAX_INPUT_CHARS=12000

# Max tokens for the extraction response.
DEBATE_SCAN_MAX_TOKENS=600

# Cap on tracked entries per channel; oldest resolved (then oldest unresolved) drop first.
DEBATE_MAX_PER_CHANNEL=15

# Max entries injected into the system prompt per call.
DEBATE_INJECT_MAX=3

# Minimum days between surfacing the same entry, so the bot doesn't repeat callbacks.
DEBATE_SURFACE_COOLDOWN_DAYS=3

# Model used for extraction. Defaults to MODEL_CHAT if unset.
# DEBATE_MODEL=gpt-6-luna


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
# SUMMARY_MODEL=gpt-6-luna

# Max tokens in the summary output.
SUMMARY_MAX_TOKENS=500

# Max chars of chat history fed to the summarizer per run. Caps cost on active channels.
SUMMARY_MAX_INPUT_CHARS=12000


# ─────────────────────────────────────────────
# Reminders
# ─────────────────────────────────────────────

# Poll interval (seconds) for checking due reminders. Stored in data/reminders.json (gitignored).
REMINDER_CHECK_SECONDS=30


# ─────────────────────────────────────────────
# The Morning Paper
# ─────────────────────────────────────────────

# Comma-separated channels that get a daily in-character recap. Unset = feature disabled.
# MORNING_PAPER_CHANNEL_IDS=123456789

# Server-local hour at/after which the daily edition posts.
MORNING_PAPER_HOUR=9

# Skip the day's edition below this many messages in the last 24h.
MORNING_PAPER_MIN_MESSAGES=15

# Input/output caps for the recap LLM call.
MORNING_PAPER_MAX_INPUT_CHARS=12000
MORNING_PAPER_MAX_TOKENS=600


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
MINECRAFT_VANILLA_CONNECT_URL=play.example.com   # shown as "Connect: ..." in the panel (free text)

# Modded runs as a systemd *user* service on a desktop PC (the Docker host can't run it
# well) — see "Scoped SSH access" for the one-time PC setup.
MINECRAFT_MODDED_SSH_HOST=192.168.0.x        # the PC; start = `systemctl --user start` over SSH
MINECRAFT_MODDED_SSH_USER=trevor
MINECRAFT_MODDED_SERVICE=minecraft-modded    # systemd user unit name (default)
MINECRAFT_MODDED_RCON_HOST=192.168.0.x       # same PC — status/stop go over RCON
MINECRAFT_MODDED_RCON_PORT=25575
MINECRAFT_MODDED_RCON_PASSWORD=your_rcon_password
MINECRAFT_MODDED_CONNECT_URL=modded.example.com  # shown as "Connect: ..." in the panel (free text)

# Creative server — SSH + Docker log watcher + RCON, same shape as vanilla
MINECRAFT_CREATIVE_SSH_HOST=192.168.0.x
MINECRAFT_CREATIVE_SSH_USER=admin
MINECRAFT_CREATIVE_CONTAINER=minecraft-creative      # Docker container name to watch/log
MINECRAFT_CREATIVE_RCON_HOST=192.168.0.x
MINECRAFT_CREATIVE_RCON_PORT=25575
MINECRAFT_CREATIVE_RCON_PASSWORD=your_rcon_password
MINECRAFT_CREATIVE_CONNECT_URL=play.example.com

# Velocity proxy compose service in front of vanilla/creative (same host/compose dir).
# It is the only thing publishing the player port, so starting either server also
# starts the proxy (whose depends_on brings up both backends). Its online state is
# shown in the Minecraft panel and web dashboard. Set empty to disable.
MINECRAFT_PROXY_SERVICE=mc-proxy

# Discord channels for background event announcements (server start/stop, player join, etc.)
MINECRAFT_EVENTS_CHANNEL_ID=
MINECRAFT_CREATIVE_EVENTS_CHANNEL_ID=

# Kill switch for the Minecraft event watchers — checked every cycle, no restart needed.
MINECRAFT_EVENTS_ENABLED=true


# ─────────────────────────────────────────────
# Satisfactory Server
# ─────────────────────────────────────────────

SATISFACTORY_SSH_HOST=192.168.0.x            # required — remote host for start/stop
SATISFACTORY_SSH_USER=admin                  # optional SSH user
SATISFACTORY_COMPOSE_DIR=/home/data          # path to docker-compose on remote host
# SATISFACTORY_API_HOST=                     # optional — defaults to SSH host
SATISFACTORY_API_PORT=7777                   # HTTPS API port (default: 7777)
SATISFACTORY_CONNECT_URL=satisfactory.example.com:7777  # shown as "Connect" field in the panel (free text)
SATISFACTORY_EVENTS_CHANNEL_ID=              # Discord channel for milestone announcements
SATISFACTORY_EVENTS_ENABLED=true             # kill switch — checked every cycle, no restart needed

# Which servers appear in !status / /status (comma-separated).
# Matched case-insensitively against each server's *_HOSTNAME env var, or its internal
# key (minecraft_vanilla, minecraft_modded, minecraft_creative, satisfactory). Unset = all shown.
STATUS_SERVERS=minecraft_vanilla,minecraft_modded,satisfactory


# ─────────────────────────────────────────────
# Palworld Server
# ─────────────────────────────────────────────

PALWORLD_SSH_HOST=192.168.0.x                # remote host — start/stop via SSH+Docker
PALWORLD_SSH_USER=admin                      # optional SSH user
PALWORLD_COMPOSE_DIR=/home/data              # path to docker-compose on remote host
PALWORLD_CONNECT_URL=palworld.example.com:8211  # shown as "Connect" in the panel (free text)

# RuneScape: Dragonwilds — same SSH+Docker shape as Palworld. No redeploy: the image is
# built locally and its entrypoint updates the game on every start.
DRAGONWILDS_SSH_HOST=192.168.0.x
DRAGONWILDS_SSH_USER=admin
DRAGONWILDS_COMPOSE_DIR=/home/data
DRAGONWILDS_CONNECT_URL=dragonwilds.example.com:7778
# Channel for the persistent auto-refreshing status panel (and command announcements).
# Leave blank to disable both.
DRAGONWILDS_CHANNEL_ID=


# ─────────────────────────────────────────────
# Web Admin Panel (webpanel/) — see "Web Panel" section below
# ─────────────────────────────────────────────

# Signs panel session cookies. Generate with:
#   python -c "import secrets; print(secrets.token_hex(32))"
WEBPANEL_SECRET_KEY=

# Single admin login — generate the hash with:
#   python -c "from webpanel.auth import hash_password; print(hash_password('your-password'))"
WEBPANEL_USERNAME=admin
WEBPANEL_PASSWORD_HASH=

# Port the panel listens on inside the container (default: 8000).
# WEBPANEL_PORT=8000

# Public URL shown by the `/panel` bot command (free text, e.g. https://panel.ventoz.ca).
WEBPANEL_URL=

# Discord channel for web-panel action notifications (start/stop/redeploy/deploy/
# delete) on servers that don't already have a dedicated *_EVENTS_CHANNEL_ID.
PANEL_EVENTS_CHANNEL_ID=

# ── "Deploy new server" (Phase 3 — templates) ──
# Single target host for newly-deployed template instances (e.g. GameDocker).
# Each instance gets its own directory/compose file under DEPLOY_BASE_DIR — never
# touches the hand-maintained main docker-compose.yml on that host.
DEPLOY_TARGET_HOST=
DEPLOY_TARGET_USER=admin
# DEPLOY_BASE_DIR=/home/data/gameservers/deployed


# ─────────────────────────────────────────────
# EmuCoach WoW repack (Windows 11 VM, via SSH)
# ─────────────────────────────────────────────

# Requires OpenSSH Server on the VM with key auth for the bot's SSH user. If that user is
# in the local Administrators group, Windows requires the key in
# C:\ProgramData\ssh\administrators_authorized_keys (SYSTEM+Administrators-only ACL) instead
# of the usual per-user authorized_keys file.
EMUCOACH_SSH_HOST=
EMUCOACH_SSH_USER=

# Repack root on the VM.
EMUCOACH_DIR=C:\GameServers\CATASILVER

# Start targets relative to EMUCOACH_DIR. .bat/.cmd files are wrapped in cmd /c.
EMUCOACH_DB_START=Database\start_mysql.bat
EMUCOACH_AUTH_START=Repack\authserver.exe
EMUCOACH_WORLD_START=Repack\worldserver.exe

# Seconds to wait after starting the database before launching auth/world.
# A cold MySQL start can easily take 20+ seconds — err on the high side.
EMUCOACH_DB_WAIT=30

# Optional: shown as "Connect: ..." in status messages.
EMUCOACH_CONNECT_URL=


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

### Local (virtualenv)

```bash
source .venv/bin/activate
python main.py
```

### Docker

Requires Docker and Docker Compose.

**First time setup — give the bot its own scoped SSH key** (see "Scoped SSH access" below). The container mounts `./ssh` — a bot-only key and `known_hosts` — never your personal `~/.ssh`.

A `docker-compose.yml` is included at the project root:

```yaml
services:
  bot:
    build: .
    env_file: .env
    restart: unless-stopped
    ports:
      - "8000:8000"            # web admin panel — see "Web Panel" section
    volumes:
      - ./data:/app/data       # persistent state (ChromaDB, profiles, debates, reminders, logs, deployed-server metadata)
      - ./ssh:/root/.ssh:ro    # bot-only SSH key + known_hosts (gitignored, see "Scoped SSH access")
```

**Build and run:**

```bash
docker compose up --build
```

Run in the background:

```bash
docker compose up --build -d
```

**Deploying to another server:** copy the project folder, recreate `.env` (it is gitignored), and run `docker compose up --build`. The `./data` volume path is relative so no compose edits are needed.

**`.env` changes in Docker:** values reach the container only when it is *created*, so run `docker compose up -d` after editing `.env` — `docker compose restart` keeps the old values. (Running locally, most values are re-read on every call.) From a dev machine, `scripts/prod-env.sh show|set|unset KEY[=VALUE]` does the edit (with a timestamped backup and secret masking) and the recreate in one step over SSH.

**Updating a running deployment** (pull latest code and pick up any `.env` changes):

```bash
git pull
docker compose up --build -d
```

Bot state (ChromaDB, profiles, debates, reminders, Morning Paper state, logs) is persisted in `./data` on the host via a bind mount and survives container restarts.

### Scoped SSH access

The bot SSHes into game hosts to run `docker compose` and friends. It gets a dedicated key that works only from the bot's host and — on Linux hosts — only for the exact commands it sends, enforced by `deploy/bot-ssh-gate.sh` as an `authorized_keys` forced command. A leaked key can start/stop/redeploy game servers and manage web-panel deployments; it cannot open a shell, read files, or reach any host that isn't listed here.

Docker access is root-equivalent on a host regardless (a crafted compose file can mount `/`), so keep the key off hosts that don't run game servers.

**1. On the bot host** (in the project directory):

```bash
mkdir -m 700 ssh
ssh-keygen -t ed25519 -N '' -C discord-bot -f ssh/id_ed25519
# Copy already-verified host keys rather than trusting a fresh scan:
for h in <game-host-ip> <emucoach-vm-ip>; do ssh-keygen -F "$h" -f ~/.ssh/known_hosts | grep -v '^#'; done > ssh/known_hosts
chmod 600 ssh/id_ed25519 ssh/known_hosts
cat ssh/id_ed25519.pub
```

**2. On each Linux game host** (as the `*_SSH_USER`):

```bash
sudo install -m 755 bot-ssh-gate.sh /usr/local/bin/bot-ssh-gate   # copy deploy/bot-ssh-gate.sh over first
```

Then add one line to `~/.ssh/authorized_keys` — arguments are `DEPLOY_BASE_DIR` first, then every `*_COMPOSE_DIR` the bot uses on that host:

```
restrict,from="<bot-host-ip>",command="/usr/local/bin/bot-ssh-gate /home/data/gameservers/deployed /home/data" ssh-ed25519 AAAA... discord-bot
```

Refused commands are logged to syslog under `bot-ssh-gate` (`journalctl -t bot-ssh-gate`).

**3. On the EmuCoach Windows VM:** the bot sends encoded PowerShell, which can't be allowlisted, so the key is restricted by source address only. Add to `C:\ProgramData\ssh\administrators_authorized_keys` (admin user) or the user's `authorized_keys`:

```
from="<bot-host-ip>" ssh-ed25519 AAAA... discord-bot
```

**3b. On a desktop PC hosting a systemd-user game server** (modded Minecraft): install the unit and the systemd gate as that user — no sudo needed:

```bash
cp deploy/minecraft-modded.service ~/.config/systemd/user/ && systemctl --user daemon-reload
install -m 755 deploy/bot-ssh-gate-systemd.sh ~/.local/bin/bot-ssh-gate-systemd
loginctl enable-linger "$USER"   # lets the unit run while logged out
```

`~/.ssh/authorized_keys` line (units to allow go after the gate path):

```
restrict,from="<bot-host-ip>",command="/home/<user>/.local/bin/bot-ssh-gate-systemd minecraft-modded" ssh-ed25519 AAAA... discord-bot
```

Add the PC's host key to the bot's `ssh/known_hosts`, and let the bot host reach the PC on 22 (SSH) and the RCON port through the PC's firewall. Server console: `journalctl --user -u minecraft-modded -f`.

**4. Switch over:** `docker compose up --build -d`, then exercise start/stop/status for each server and a web-panel deploy/delete. Check `journalctl -t bot-ssh-gate` on the game host for any `DENIED` lines.

## Testing

Pure-logic test suite (pytest + pytest-asyncio) — no Discord, network, or ChromaDB connection needed:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Covers history building, storage filters, retrieval decay, chat helpers, the agentic tool loop (scripted fake model), the `REASONING_EFFORT` wrapper, reminders, profile and debate extraction (structured-output parsing), Morning Paper scheduling, Minecraft start/proxy handling and modded-via-systemd, model switching (`/model` overrides and picker), usage/cost recording, the blank-reply guard, the web panel (auth + login lockout, dashboard, deploy flow, store, templates), and both SSH gate scripts (allowed command shapes generated from the real `DockerComposeGameServer` / `RemoteUserService`, plus injection/traversal attempts).

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
| `!missed` | `/missed` | Catch up on what happened since you were last here |
| `!summarize` | `/summarize` | TL;DR of recent conversation |
| `!cleardocs` | `/cleardocs` | Remove stored documents (keeps message history) |
| `!clearall` | — | Wipe all memory for this channel (requires Manage Messages) |
| `!whoami` | `/whoami` | See the profile facts stored about you |
| `!forget <n\|all>` | `/forget` | Delete one stored fact about you, or all of them |

### Reminders

| Prefix | Slash | Description |
|---|---|---|
| `!remind <duration> <text>` | `/remind` | Set a reminder (s/m/h/d/w, compounds like `1h30m`); delivered in character |
| `!reminders` | `/reminders` | List your pending reminders |
| `!unremind <id>` | `/unremind` | Cancel one of your reminders |

### Images

| Prefix | Slash | Description |
|---|---|---|
| `!generate <prompt>` | `/generate` | Generate an image (current image model — see `/model`) |
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
| `!status` | `/status` | Live status embed for all configured game servers |
| `!minecraft` | `/minecraft` | Open the Minecraft server panel (vanilla/modded status, player counts, proxy status) |
| `!satisfactory` | `/satisfactory` | Open the Satisfactory server panel |
| `!start_emucoach` | `/emucoach start` | Start the EmuCoach WoW server (database → auth → world) |
| `!stop_emucoach` | `/emucoach stop` | Stop the EmuCoach WoW server |
| `!emucoach_status` | `/emucoach status` | Check EmuCoach WoW server status |
| `!start_dragonwilds` | `/dragonwilds start` | Start the RuneScape: Dragonwilds server |
| `!stop_dragonwilds` | `/dragonwilds stop` | Stop the RuneScape: Dragonwilds server |
| `!dragonwilds_status` | `/dragonwilds status` | Check Dragonwilds server status |
| — | `/panel` | Get the link to the web admin panel (`WEBPANEL_URL`) |

### Misc

| Prefix | Slash | Description |
|---|---|---|
| `!commands` / `!help` | `/commands` / `/help` | Show all bot commands with descriptions |
| `!model` | `/model` | See or switch the chat and image models (dropdowns; applies bot-wide) |
| `!usage` | `/usage` | Estimated OpenAI spend: today, 7 and 30 days, by feature and model |
| `!sandwich` | `/sandwich` | Generate a random sandwich with an AI image |

## Architecture

```
main.py                       — bot init, shared state, load_extension calls; runs the bot and
                                the web panel concurrently in one asyncio loop
cogs/
  chat.py                     — on_message/on_reaction_add queue-based handler; RAG
                                integration; profile/debate context injection and
                                background extraction; summarizer/debate/Morning Paper
                                loop startup
  chat_tools.py                — AI tool schemas and executors (generate/transform/search/
                                suggest/restart); shared by the text and reaction paths
  images.py                   — generate, transform, image commands
  personality.py              — prefix + slash personality commands
  games.py                    — game, snake, adventure commands
  servers.py                  — minecraft, satisfactory, emucoach,
                                dragonwilds server commands; posts/refreshes the persistent
                                Dragonwilds panel on_ready
  reminders.py                 — remind, reminders, unremind commands
  fun.py                      — commands/help (formatted text list), simulate, sandwich
  models.py                    — /model (model picker dropdowns) and /usage (spend summary)
  rag.py                      — learn, memory, missed, summarize, cleardocs, clearall,
                                whoami, forget
AIfunc/
  responses.py                — BASE_SYSTEM_PROMPT; generate_gpt_response (agentic tool
                                loop, rag_context, user_context, debate_context, tools,
                                auto_resolve), analyze_image, generate_image, transform_image
  simulate.py                 — ConversationSimulator (via async_chat_completion)
chatbotfunc/
  logger.py                   — setup_logging(): RotatingFileHandler → data/bot.log
  utils.py                    — fetch_message_history, describe_extras, async_chat_completion
                                (applies REASONING_EFFORT to every chat call),
                                split_message, format_error_message, encode_discord_image,
                                encode_video_frames, SUPPORTED_DOC_EXTENSIONS
  personalitymanager.py       — PersonalityManager: data/personalities.json store;
                                auto-migrates from .env on first run; per-channel pin
                                cache in data/channel_personalities.json
  profiles.py                 — get_user_context(), extract_and_update(), get_facts(),
                                delete_fact(), clear_facts(); reads/writes
                                data/user_profiles.json (gitignored)
  summarizer.py                — summarizer_loop(), summarize_channel(); skip/force logic;
                                state in data/summarizer_state.json (gitignored)
  debates.py                   — debate_scanner_loop(), scan_channel(), get_debate_context(),
                                mark_surfaced(); state in data/debates.json (gitignored)
  reminders.py                 — reminder store, parse_duration/format_duration,
                                reminder_loop(); state in data/reminders.json (gitignored)
  morning_paper.py             — morning_paper_loop(): daily in-character recap per
                                channel; state in data/morning_paper_state.json (gitignored)
  model_settings.py            — curated chat/image model lists; runtime overrides in
                                data/model_settings.json win over MODEL_CHAT / IMAGE_MODEL
  usage.py                     — per-call token/cost recording (price table) into
                                data/usage.json; summarize() for /usage
ragfunc/
  memory.py                   — ChannelMemory (ChromaDB singleton client); store_message
                                (context_snippet support), store_document, retrieve
                                (decay + before_ts filter), get_expiring, delete_by_ids,
                                clear methods; list_channel_ids(); async helpers
gamefunc/
  adventure.py / adventure_panel.py  — 55×23 ASCII dungeon, viewport renderer, D-pad UI
  snake.py / snake_panel.py    — Snake game, D-pad buttons, score tracking
  tictactoe.py                — Tic-Tac-Toe logic
  minecraft.py / minecraft_panel.py  — thread-safe RCON; vanilla/creative start via
                                SSH+Docker (also starts the Velocity proxy), modded via a
                                systemd user service on the desktop PC; live status panel
                                incl. proxy state
  minecraft_events.py          — SSH + `docker logs -f` event watcher per server
                                (vanilla/creative); idles while offline/disabled
  satisfactory.py             — SSH+Docker start/stop; HTTPS API state (players, tier,
                                play time, tick rate); token caching with auto-refresh
  satisfactory_panel.py       — Satisfactory management panel (Start/Stop/Restart/Refresh)
  satisfactory_monitor.py      — polls the API for tech-tier milestones, announces them
  emucoach.py                   — starts/stops the EmuCoach WoW repack on a Windows VM over
                                SSH; processes spawned detached via WMI (Win32_Process Create)
  status_panel.py             — read-only all-servers status embed; parallel queries;
                                configurable via STATUS_SERVERS env var
  user_service.py             — RemoteUserService: `systemctl --user start|stop|is-active`
                                over SSH, for game servers hosted on a desktop PC
  compose_server.py           — DockerComposeGameServer: shared SSH+docker-compose
                                start/stop/pull_and_redeploy/is_running, used by Satisfactory,
                                Palworld, Minecraft vanilla/creative, and webpanel deploys
  palworld.py                  — PalworldServer: SSH+Docker start/stop/redeploy for Palworld;
                                status via `docker inspect` (no stateless status API configured)
  dragonwilds.py / dragonwilds_panel.py — DragonwildsServer (SSH+Docker start/stop/status, no
                                redeploy) and its persistent auto-refreshing channel panel
webpanel/                      — browser admin panel; runs in-process with the bot (see main.py)
  app.py                       — FastAPI app factory; session middleware, router wiring
  auth.py                       — single-admin login (WEBPANEL_USERNAME/_PASSWORD_HASH), session
                                cookie signed by WEBPANEL_SECRET_KEY, require_login dependency,
                                per-IP lockout after 5 failed logins in 15 min
  routes_servers.py            — dashboard for the fixed servers above (status/start/stop/redeploy)
  routes_deploy.py             — "Deploy new server" flow: template catalog, port-collision
                                check, compose-file generation, and management of what's deployed
  templates_catalog.py         — curated game templates (Terraria, Valheim/Docker) + a generic
                                custom-image template; render_compose_yaml()
  store.py                     — data/deployed_servers.json: metadata for template-deployed instances
  templates/, static/           — Jinja2 HTML + CSS; htmx (CDN) for in-place refresh, no JS build step
funfunc/
  image_search.py             — Google Custom Search wrapper
  web_search.py               — Tavily web search (AI google_search tool)
  sandwich.py                 — random sandwich generator
deploy/
  bot-ssh-gate.sh              — authorized_keys forced command for Docker game hosts; only runs
                                the exact remote commands the bot sends (see Scoped SSH access)
  bot-ssh-gate-systemd.sh      — same idea for the desktop PC: only systemctl --user
                                start/stop/is-active on listed units
  minecraft-modded.service     — systemd user unit for the PC-hosted modded server
scripts/
  prod-env.sh                  — show/set/unset keys in the deployed .env (backup, secret
                                masking, container recreate)
tests/                         — pytest + pytest-asyncio; pure-logic coverage, no live services
ssh/                           — bot-only SSH key + known_hosts, mounted into the container
                                (gitignored; see Scoped SSH access)
data/                         — runtime artifacts (gitignored in full)
  chroma/                     — ChromaDB persistent vector store
  personalities.json          — personality descriptor list + active selection
  channel_personalities.json  — per-channel personality pin map
  user_profiles.json          — per-user extracted fact profiles
  debates.json                 — tracked debates/running jokes per channel
  model_settings.json          — /model overrides for the chat and image model
  usage.json                   — per-day token/cost totals by feature and model
  reminders.json               — pending reminders
  morning_paper_state.json     — last-posted-date per channel, prevents double posting
  summarizer_state.json       — last-summary timestamps per channel
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

**Image/video/sticker analysis:** when you share an image, short video, sticker, or lone custom emoji in an allowed channel, the bot describes it in character and stores the description in RAG so it can reference it in future conversations.

**File auto-storage:** dropping a supported file in an allowed channel stores it in RAG automatically. Supported types: `.txt .py .md .js .ts .jsx .tsx .json .csv .yaml .yml .html .css .sh .toml .ini .cfg .pdf`

PDFs are text-extracted via `pypdf`. Scanned/image-only PDFs won't have usable text.

**Auto-summarization:** a background task runs every `SUMMARY_INTERVAL_HOURS` (default: 24) and scans all channels. When messages are approaching their TTL expiry, they are condensed into a permanent summary document and then deleted. Skip/force logic: skip if fewer than `SUMMARY_MIN_NEW_MESSAGES` are expiring and a summary ran within `SUMMARY_FORCE_AFTER_DAYS` days — after that window, summarize regardless so nothing expires uncaptured. This makes effective memory infinite while keeping the RAG index clean.

## User Profiles

After every real text exchange, a lightweight background LLM call extracts new facts about the user from the conversation (preferences, games, habits, running jokes, anything distinctive) and merges them into `data/user_profiles.json`. The call uses a strict JSON-schema `response_format`, so the output shape is guaranteed rather than parsed out of free text; a cheap model (`USER_PROFILE_MODEL=gpt-6-luna`) handles it as well as the chat model. On the next message from that user, the profile is injected into the system prompt as a `USER PROFILE:` section before RAG context, so the model knows who it's talking to without relying on retrieval.

Profiles are per-user (keyed by Discord user ID) and persist indefinitely. The `USER_PROFILE_MAX_FACTS` cap (default: 20) keeps profiles from bloating — the oldest facts are dropped when it's hit, keeping the most recently learned information. `!whoami` / `/whoami` shows the current list; `!forget <n>` / `/forget` removes one fact, `!forget all` clears everything. Gitignored; never committed.

## Debates & Running Jokes

A background scanner (`DEBATE_SCAN_INTERVAL_HOURS`, default: 12) pulls each channel's recent history directly from Discord and sends it to an LLM that returns `new` / `update` / `resolve` actions (strict JSON-schema output) against the channel's tracked list in `data/debates.json`. A truncated response is dropped without advancing the scan window, so the next scan retries it. Unresolved entries that haven't been surfaced within `DEBATE_SURFACE_COOLDOWN_DAYS` (default: 3) are injected into the system prompt as an `ONGOING THREADS YOU REMEMBER:` section — the model is told to bring one up only if it genuinely fits, never to force it. After a response is sent, topic words are fuzzy-matched against the response text to stamp `last_surfaced_ts` and prevent immediate repeats.

## The Morning Paper

An optional daily in-character recap, posted to each channel listed in `MORNING_PAPER_CHANNEL_IDS` at/after `MORNING_PAPER_HOUR` server-local time. Pulls the last 24 hours of history plus ongoing-threads context and asks the LLM for a punchy recap in the channel's active personality. Skips the day's edition if fewer than `MORNING_PAPER_MIN_MESSAGES` were posted. `data/morning_paper_state.json` prevents double-posting across restarts/reconnects. Unset the channel list to disable the feature entirely.

## Personality System

`BASE_SYSTEM_PROMPT` in `AIfunc/responses.py` defines platform-level rules applied to every personality: Discord context, no hollow filler openers, code block formatting, RAG context handling, history handling, stay-in-character, and uncertainty behaviour.

Personalities are stored in `data/personalities.json` as a list of plain text descriptors. On first run, the bot auto-migrates any `PERSONALITY=` entries from `.env` into this file so existing personalities are preserved. After migration, `.env` entries are ignored.

Each descriptor is a short character description injected at the `{personality}` slot in `BASE_SYSTEM_PROMPT`. Keep them short — the base prompt handles all boilerplate:
- `a sarcastic, reluctant assistant named Soupy Dafoe preoccupied with soup`
- `Professor Hubert J. Farnsworth from Futurama — exclamatory, brilliantly absent-minded`
- `a DnD-style Sorceress who must roll a dice and announce the result before any action`

Use `!pin [n]` / `/personality pin [n]` to lock a specific personality to a channel. Pins are stored in `data/channel_personalities.json` and survive restarts. Remove with `!unpin` / `/personality unpin`.

## Web Panel

A browser dashboard (`webpanel/`) for everything in [Game Servers](#game-servers) above, plus deploying new ones. It runs inside the same process as the bot (`main.py` runs `bot.start()` and `uvicorn.Server.serve()` concurrently), so it shares `.env`, the bot's scoped SSH key, and the `gamefunc/` control classes — no separate service or duplicated config.

**Setup:**

1. Generate a session-signing secret and set it as `WEBPANEL_SECRET_KEY`:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Pick a `WEBPANEL_USERNAME` and generate its password hash for `WEBPANEL_PASSWORD_HASH`:
   ```bash
   python -c "from webpanel.auth import hash_password; print(hash_password('your-password'))"
   ```
3. The panel listens on `WEBPANEL_PORT` (default `8000`) inside the container. Five failed logins from one IP within 15 minutes lock that IP out until the oldest failure ages out (in-memory; behind a reverse proxy all requests share the proxy's IP, which is fine for a single admin). Reverse-proxy it behind your own auth/TLS layer — do **not** expose it directly to the internet unauthenticated. This panel can reach every configured host over SSH and Windows VM over WMI, so treat it as sensitive as SSH access itself; an IP allowlist at the reverse proxy (in addition to the login) is a reasonable extra layer given the blast radius.
4. Optionally set `WEBPANEL_URL` so `/panel` in Discord can post the link.

**Dashboard:** live status + Start/Stop/Redeploy for Minecraft vanilla/creative (rows also show the Velocity proxy's online state) and modded (no redeploy — PC-hosted), Satisfactory, Palworld, RuneScape: Dragonwilds (no redeploy — built image that updates on start), and EmuCoach — wrapping the same `gamefunc/` classes the Discord commands use, so state is always consistent between the two surfaces. Rows auto-refresh every 15s via htmx polling, no page reload.

**Deploy new server:** `/deploy` offers a small catalog of curated templates (see `webpanel/templates_catalog.py`) plus a "custom image" template for anything not curated. Deploying:
1. Validates the instance name and checks the requested port(s) aren't already bound on `DEPLOY_TARGET_HOST` (a live `ss -tuln` check over SSH).
2. Renders a standalone `docker-compose.yml` into its own directory under `DEPLOY_BASE_DIR` — never touches the hand-maintained compose file already running Minecraft/Satisfactory/Palworld on that host.
3. Runs `docker compose up -d` and records the instance in `data/deployed_servers.json`.

Deployed instances then appear on the dashboard like any fixed server (start/stop/redeploy), plus a **Delete** action that requires typing the instance's name to confirm — it stops the container, runs `docker compose down`, and removes its directory from the host.

**Discord integration:** panel actions (start/stop/redeploy/deploy/delete) post a short line to the same channel the affected server's own event watcher already announces to (`MINECRAFT_EVENTS_CHANNEL_ID`, etc.), falling back to `PANEL_EVENTS_CHANNEL_ID` — so a server started from the browser shows up in Discord exactly like one started with `!minecraft`.

**Curated template images/volume paths are a starting point, not a guarantee** — third-party game server images vary in their conventions. The deploy form exposes the data volume path as an editable field for exactly this reason; check the image's own docs on first deploy.

## Known Limitations

- **Modded Minecraft needs the PC on** — it runs on the desktop PC, not the Docker host, so start fails (with a clear message) while that PC is off or asleep. Players connect to it directly, not through the Velocity proxy — Fabric servers need extra mods to sit behind Velocity.
- **EmuCoach requires OpenSSH Server on the target Windows VM**, set up in advance with key auth for the bot's SSH user (see the `.env` section above for the admin-group nuance). Nothing in the bot can install or configure this remotely.
- **Image transform state** — `!transform last` and AI-triggered transforms require at least one `!generate` or `!transform` in the current session. Image bytes live in memory and are lost on restart.
- **Scanned PDFs** — `!learn` and file auto-storage extract text via `pypdf`. Image-only/scanned PDFs produce no usable text.
- **Token estimate** — `MAX_CONTEXT_TOKENS` trimming uses a chars÷4 approximation. Give yourself headroom when setting the cap.
- **Profile extraction latency** — user profiles are updated in the background after each response. A fact mentioned in message N is available starting from message N+1, not immediately.
- **Summarizer/debate scanner first run** — these background loops start their first scan after their interval has elapsed, not immediately on startup.
- **RAG memory is per-channel** — each Discord channel has its own isolated collection. `!clearall` only affects the current channel.
