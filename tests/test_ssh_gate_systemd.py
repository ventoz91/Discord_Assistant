"""deploy/bot-ssh-gate-systemd.sh: forced-command allowlist on the PC that
hosts systemd-user game servers. Commands are generated from the real
RemoteUserService so drift between the two fails here."""

import os
import pathlib
import subprocess

import pytest

from gamefunc.user_service import RemoteUserService

GATE = pathlib.Path(__file__).resolve().parent.parent / "deploy" / "bot-ssh-gate-systemd.sh"


@pytest.fixture
def bindir(tmp_path):
    for tool, body in (("systemctl", 'echo "systemctl $*"'), ("logger", "exit 0")):
        f = tmp_path / tool
        f.write_text(f"#!/bin/sh\n{body}\n")
        f.chmod(0o755)
    return tmp_path


def gate(bindir, command, units=("minecraft-modded",)):
    return subprocess.run(
        ["bash", str(GATE), *units],
        env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "SSH_ORIGINAL_COMMAND": command},
        capture_output=True, text=True, timeout=10,
    )


async def test_real_service_commands_pass(bindir, monkeypatch):
    monkeypatch.setenv("H", "10.0.0.5")
    svc = RemoteUserService("H", "U", "UNIT", default_unit="minecraft-modded")
    sent = []

    async def fake_exec(*argv, **kw):
        sent.append(argv[-1])
        raise RuntimeError("stop here")

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    for verb in ("start", "stop", "is_active"):
        with pytest.raises(RuntimeError):
            await getattr(svc, verb)()
    assert sent == ["systemctl --user start minecraft-modded",
                    "systemctl --user stop minecraft-modded",
                    "systemctl --user is-active minecraft-modded"]
    for cmd in sent:
        r = gate(bindir, cmd)
        assert r.returncode == 0 and r.stdout.strip() == cmd, (cmd, r.stderr)


@pytest.mark.parametrize("cmd", [
    "",
    "bash",
    "id",
    "systemctl --user start other-unit",
    "systemctl start minecraft-modded",                  # system scope
    "systemctl --user restart minecraft-modded",         # verb not allowed
    "systemctl --user edit minecraft-modded",
    "systemctl --user start minecraft-modded; id",
    "systemctl --user start minecraft-modded && id",
    "systemctl --user start minecraft-modded other",
    "systemctl --user start $(id)",
    "systemctl --user start ../minecraft-modded",
])
def test_refused(bindir, cmd):
    r = gate(bindir, cmd)
    assert r.returncode == 126, (cmd, r.stdout)
    assert "systemctl" not in r.stdout


def test_needs_unit_args(bindir):
    assert gate(bindir, "systemctl --user start minecraft-modded", units=()).returncode == 2
