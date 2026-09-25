#!/usr/bin/env bash
# Edit the live bot's .env on the deploy host, then recreate the container so
# the change takes effect (env_file is only read at container creation — a
# plain `docker compose restart` keeps the old values).
#
#   scripts/prod-env.sh show KEY [KEY...]         print values (secrets masked)
#   scripts/prod-env.sh set KEY=VALUE [KEY=VALUE...]
#   scripts/prod-env.sh unset KEY [KEY...]
#
# set/unset back up .env to .env.bak-<timestamp> first, replace an existing
# KEY line in place (dropping duplicates) or append it, then run
# `docker compose up -d` and print the container's resulting values.
#
# Deliberately narrow so it can be allow-listed for Claude Code without
# granting general SSH access: one host, one file, one compose project, and
# values of secret-looking keys are never printed.
#
# Override with PROD_ENV_HOST / PROD_ENV_DIR if the bot ever moves.

set -euo pipefail

HOST="${PROD_ENV_HOST:-local1}"
DIR="${PROD_ENV_DIR:-/home/data/Discord_Bot}"

usage() { sed -n '6,8p' "$0" | sed 's/^# *//' >&2; exit 2; }
[ "$#" -ge 2 ] || usage
action="$1"; shift
case "$action" in show|set|unset) ;; *) usage ;; esac

for arg in "$@"; do
    key="${arg%%=*}"
    [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || { echo "bad key: $key" >&2; exit 2; }
    if [ "$action" = set ] && [[ "$arg" != *=* ]]; then echo "set needs KEY=VALUE: $arg" >&2; exit 2; fi
    if [ "$action" != set ] && [[ "$arg" == *=* ]]; then echo "$action takes bare keys: $arg" >&2; exit 2; fi
    [[ "$arg" != *$'\n'* ]] || { echo "newlines not allowed: $key" >&2; exit 2; }
done

# The remote side is a fixed Python program read from stdin; the arguments
# travel as base64 so no value is ever interpreted by a remote shell.
payload=$(printf '%s\0' "$action" "$DIR" "$@" | base64 -w0)

ssh -o BatchMode=yes "$HOST" "python3 - $payload" <<'PY'
import base64, os, re, shutil, subprocess, sys, time

action, directory, *args = base64.b64decode(sys.argv[1]).decode().split("\0")[:-1]
env_path = os.path.join(directory, ".env")
SECRET = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|HASH|PASS\b")

def mask(key, value):
    return "********" if SECRET.search(key) and value and value != "<unset>" else value

def read_lines():
    with open(env_path) as f:
        return f.read().splitlines()

def show(keys, source):
    for k in keys:
        print(f"{k}={mask(k, source.get(k, '<unset>'))}")

if action == "show":
    values = {}
    for line in read_lines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
        if m:
            values[m.group(1)] = m.group(2)  # last wins, like docker env_file
    show(args, values)
    sys.exit(0)

updates = dict(a.split("=", 1) for a in args) if action == "set" else {k: None for k in args}
backup = f"{env_path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
shutil.copy2(env_path, backup)

out, written = [], set()
for line in read_lines():
    m = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
    key = m.group(1) if m else None
    if key in updates:
        if updates[key] is not None and key not in written:
            out.append(f"{key}={updates[key]}")
            written.add(key)
        continue  # unset, or a duplicate of a key already written
    out.append(line)
for key, value in updates.items():
    if value is not None and key not in written:
        out.append(f"{key}={value}")

tmp = env_path + ".tmp"
with open(tmp, "w") as f:
    f.write("\n".join(out) + "\n")
shutil.copymode(env_path, tmp)
os.replace(tmp, env_path)
print(f"backup: {backup}")

r = subprocess.run(["docker", "compose", "up", "-d"], cwd=directory, capture_output=True, text=True)
print((r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else "")
if r.returncode != 0:
    print("docker compose up -d FAILED — .env was changed; restore from the backup above if needed")
    sys.exit(1)

container = subprocess.run(["docker", "compose", "ps", "-q"], cwd=directory, capture_output=True, text=True).stdout.split()
if container:
    env = subprocess.run(["docker", "inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", container[0]],
                         capture_output=True, text=True).stdout
    live = dict(l.split("=", 1) for l in env.splitlines() if "=" in l)
    print("container now has:")
    show(list(updates), live)
PY
