#!/usr/bin/env bash
# SSH forced-command gate for the Discord bot's key on a machine where game
# servers run as systemd *user* services (the desktop PC hosting modded
# Minecraft). Companion to bot-ssh-gate.sh, which covers the Docker hosts.
#
#   restrict,from="10.13.37.100",command="/home/trevor/.local/bin/bot-ssh-gate-systemd minecraft-modded" ssh-ed25519 AAAA... discord-bot
#
# Usage: bot-ssh-gate-systemd UNIT [UNIT...]
#
# Only `systemctl --user start|stop|is-active <UNIT>` for a listed unit is
# run (as argv, never through a shell); anything else is refused and logged.
# The key can't open a shell, read files, or touch any other unit.

set -uo pipefail

CMD="${SSH_ORIGINAL_COMMAND:-}"

log() { logger -t bot-ssh-gate -- "$*" 2>/dev/null || true; }
deny() {
    log "DENIED: $CMD"
    echo "bot-ssh-gate: command not allowed" >&2
    exit 126
}

if [ "$#" -lt 1 ]; then
    echo "usage: bot-ssh-gate-systemd UNIT [UNIT...]" >&2
    exit 2
fi

[[ "$CMD" =~ ^systemctl\ --user\ (start|stop|is-active)\ ([A-Za-z0-9_.@-]+)$ ]] || deny
verb="${BASH_REMATCH[1]}"
unit="${BASH_REMATCH[2]}"

allowed=0
for u in "$@"; do
    [ "$unit" = "$u" ] && allowed=1
done
[ "$allowed" -eq 1 ] || deny

# A forced-command session may lack the user bus variables systemctl --user
# needs; pam_systemd normally sets XDG_RUNTIME_DIR, this covers when it doesn't.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

[ "$verb" = is-active ] || log "ALLOWED: $CMD"
exec systemctl --user "$verb" "$unit"
