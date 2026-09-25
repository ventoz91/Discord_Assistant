"""deploy/bot-ssh-gate.sh: the forced-command allowlist on game hosts.

Allowed commands are generated from the real DockerComposeGameServer where
possible, so a change to the command shapes the bot sends breaks this test
instead of silently breaking production. docker/ss/logger are stubbed on PATH.
"""

import os
import pathlib
import shlex
import subprocess

import pytest

from gamefunc.compose_server import DockerComposeGameServer

GATE = pathlib.Path(__file__).resolve().parent.parent / "deploy" / "bot-ssh-gate.sh"


@pytest.fixture
def env(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("docker", "ss"):
        stub = bindir / tool
        stub.write_text(f'#!/bin/sh\necho "{tool} $*"\necho "cwd=$(pwd)"\n')
        stub.chmod(0o755)
    (bindir / "logger").write_text("#!/bin/sh\nexit 0\n")
    (bindir / "logger").chmod(0o755)
    compose = tmp_path / "compose"
    compose.mkdir()
    deploy_base = tmp_path / "deployed"
    deploy_base.mkdir()
    return {"bin": bindir, "compose": str(compose), "deploy": str(deploy_base)}


def gate(env, command, stdin=None):
    return subprocess.run(
        ["bash", str(GATE), env["deploy"], env["compose"]],
        env={**os.environ, "PATH": f"{env['bin']}:{os.environ['PATH']}",
             "SSH_ORIGINAL_COMMAND": command},
        input=stdin, capture_output=True, text=True, timeout=10,
    )


async def sent_commands(server: DockerComposeGameServer) -> list[tuple[str, str | None]]:
    """Every remote command string the server object would send over SSH."""
    sent = []

    async def fake_ssh_run(cmd, timeout=30, input_text=None):
        sent.append((cmd, input_text))
        return True, "true"

    server._ssh_run = fake_ssh_run
    await server.start()
    await server.stop()
    await server.pull_and_redeploy()
    await server.down()
    await server.is_running()
    return sent


class TestAllowed:
    async def test_fixed_server_commands(self, env):
        server = DockerComposeGameServer("h", "u", env["compose"], "palworld", "palworld-server")
        for cmd, _ in await sent_commands(server):
            r = gate(env, cmd)
            assert r.returncode == 0, (cmd, r.stderr)
        assert f"cwd={env['compose']}" in gate(env, f"cd {env['compose']} && docker compose up -d palworld").stdout

    async def test_deployed_instance_lifecycle(self, env, tmp_path):
        inst_dir = f"{env['deploy']}/my-server"
        server = DockerComposeGameServer("h", "u", inst_dir, "my-server")
        write = []

        async def capture(cmd, timeout=15, input_text=None):
            write.append((cmd, input_text))
            return True, ""

        server._ssh_run = capture
        await server.write_file(f"{inst_dir}/docker-compose.yml", "services: {}\n")
        cmd, content = write[0]
        assert gate(env, cmd, stdin=content).returncode == 0
        assert pathlib.Path(inst_dir, "docker-compose.yml").read_text() == "services: {}\n"

        for cmd, _ in await sent_commands(DockerComposeGameServer("h", "u", inst_dir, "my-server")):
            assert gate(env, cmd).returncode == 0, cmd

        assert gate(env, f"rm -rf {shlex.quote(inst_dir)}").returncode == 0
        assert not pathlib.Path(inst_dir).exists()

    def test_watcher_and_port_scan(self, env):
        assert gate(env, "docker inspect -f '{{.State.Running}}' minecraft").returncode == 0
        assert gate(env, "docker logs --tail=0 -f minecraft-creative").returncode == 0
        assert gate(env, "ss -tuln").stdout.startswith("ss -tuln")


class TestDenied:
    @pytest.mark.parametrize("cmd", [
        "",
        "bash",
        "cat ~/.ssh/id_ed25519",
        "docker ps",
        "docker run --rm -v /:/host alpine sh",
        "docker compose up -d palworld",                        # no cd
        "cd /etc && docker compose up -d palworld",             # dir not allowed
        "cd {compose} && docker compose up -d palworld; id",
        "cd {compose} && docker compose up -d palworld && id",
        "cd {compose} && docker compose up -d $(id)",
        "cd {compose} && docker compose exec palworld sh",
        "cd {compose} && docker compose up -d ../palworld",
        "docker inspect -f '{{{{.State.Running}}}}' x; id",
        "docker logs --tail=0 -f x | sh",
        "ss -tuln; id",
        "rm -rf /",
        "rm -rf {deploy}",
        "rm -rf {deploy}/..",
        "rm -rf {deploy}/../compose",
        "rm -rf {deploy}/a/b",
        "rm -rf {compose}",
        "mkdir -p {deploy}/x1 && cat > /etc/cron.d/evil",
        "mkdir -p {deploy}/x1 && cat > {deploy}/x1/../../evil.yml",
        "mkdir -p /tmp/evil && cat > /tmp/evil/docker-compose.yml",
    ])
    def test_refused(self, env, cmd):
        r = gate(env, cmd.format(compose=env["compose"], deploy=env["deploy"]))
        assert r.returncode == 126, (cmd, r.stdout)
        assert "docker" not in r.stdout and "ss " not in r.stdout

    def test_deploy_base_is_not_a_regex(self, tmp_path, env):
        # A dot in DEPLOY_BASE must match only a literal dot.
        base = tmp_path / "a.b"
        base.mkdir()
        (tmp_path / "axb" / "inst").mkdir(parents=True)
        r = subprocess.run(
            ["bash", str(GATE), str(base), env["compose"]],
            env={**os.environ, "PATH": f"{env['bin']}:{os.environ['PATH']}",
                 "SSH_ORIGINAL_COMMAND": f"rm -rf {tmp_path}/axb/inst"},
            capture_output=True, text=True, timeout=10,
        )
        assert r.returncode == 126
        assert (tmp_path / "axb" / "inst").exists()
