#!/usr/bin/env bash
# SSH forced-command gate for the Discord bot's dedicated key.
#
# Installed on each Docker game host as /usr/local/bin/bot-ssh-gate and wired
# up in authorized_keys (one line, see README "Scoped SSH access"):
#
#   restrict,from="10.13.37.100",command="/usr/local/bin/bot-ssh-gate /home/data/gameservers/deployed /home/data" ssh-ed25519 AAAA... discord-bot
#
# Usage: bot-ssh-gate DEPLOY_BASE COMPOSE_DIR [COMPOSE_DIR...]
#
# sshd puts the command the bot asked for in $SSH_ORIGINAL_COMMAND. It is only
# run if it exactly matches one of the shapes the bot sends (gamefunc/
# compose_server.py, gamefunc/minecraft_events.py, webpanel/routes_deploy.py);
# anything else is refused and logged. Matched pieces are re-executed as argv,
# never handed back to a shell, so they can't smuggle in extra commands.
#
# This limits what a leaked key can do; it doesn't make docker access safe —
# `docker compose up` of a crafted compose file is still root-equivalent on
# this host. Keep the bot's key off hosts that don't run game servers.

set -uo pipefail

log() { logger -t bot-ssh-gate -- "$*" 2>/dev/null || true; }
deny() {
    log "DENIED: $CMD"
    echo "bot-ssh-gate: command not allowed" >&2
    exit 126
}

if [ "$#" -lt 2 ]; then
    echo "usage: bot-ssh-gate DEPLOY_BASE COMPOSE_DIR [COMPOSE_DIR...]" >&2
    exit 2
fi
DEPLOY_BASE="${1%/}"
shift
COMPOSE_DIRS=("$@")
CMD="${SSH_ORIGINAL_COMMAND:-}"

# Service/container names: no dots or slashes, so "..", "/" and globs can't appear.
NAME='[a-z0-9][a-z0-9_-]{0,63}'
# Deployed-instance names (webpanel/store.py NAME_RE_SOURCE).
INST='[a-z][a-z0-9-]{1,30}'

# DEPLOY_BASE/<instance> exactly — compared as a string prefix, never as a regex.
instance_dir() {
    local d="$1"
    [[ "$d" == "$DEPLOY_BASE/"* ]] || return 1
    [[ "${d#"$DEPLOY_BASE/"}" =~ ^${INST}$ ]]
}

allowed_dir() {
    local d="$1" c
    for c in "${COMPOSE_DIRS[@]}"; do
        [ "$d" = "${c%/}" ] && return 0
    done
    instance_dir "$d"
}

if [[ "$CMD" =~ ^cd\ ([^[:space:]]+)\ \&\&\ docker\ compose\ (up\ -d|stop|pull|down)\ (${NAME})$ ]]; then
    dir="${BASH_REMATCH[1]}"
    read -ra sub <<< "${BASH_REMATCH[2]}"
    svc="${BASH_REMATCH[3]}"
    allowed_dir "$dir" || deny
    log "ALLOWED: $CMD"
    cd -- "$dir" || exit 1
    exec docker compose "${sub[@]}" "$svc"

elif [[ "$CMD" =~ ^docker\ inspect\ -f\ \'\{\{\.State\.Running\}\}\'\ (${NAME})$ ]]; then
    exec docker inspect -f '{{.State.Running}}' "${BASH_REMATCH[1]}"

elif [[ "$CMD" =~ ^docker\ logs\ --tail=0\ -f\ (${NAME})$ ]]; then
    log "ALLOWED: $CMD"
    exec docker logs --tail=0 -f "${BASH_REMATCH[1]}"

elif [ "$CMD" = "ss -tuln" ]; then
    exec ss -tuln

elif [[ "$CMD" =~ ^mkdir\ -p\ ([^[:space:]]+)\ \&\&\ cat\ \>\ ([^[:space:]]+)$ ]]; then
    dir="${BASH_REMATCH[1]}"
    file="${BASH_REMATCH[2]}"
    instance_dir "$dir" || deny
    [ "$file" = "$dir/docker-compose.yml" ] || deny
    log "ALLOWED: $CMD"
    mkdir -p -- "$dir" || exit 1
    exec cat > "$file"

elif [[ "$CMD" =~ ^rm\ -rf\ ([^[:space:]]+)$ ]]; then
    dir="${BASH_REMATCH[1]}"
    instance_dir "$dir" || deny
    log "ALLOWED: $CMD"
    exec rm -rf -- "$dir"
fi

deny
