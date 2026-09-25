"""MinecraftServer.start must bring up the Velocity proxy along with the
backend — the proxy is the only thing on the player port."""

import pytest

from gamefunc.minecraft import MinecraftServer


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("MINECRAFT_VANILLA_SSH_HOST", "10.0.0.2")
    monkeypatch.setenv("MINECRAFT_VANILLA_SSH_USER", "admin")
    monkeypatch.delenv("MINECRAFT_PROXY_SERVICE", raising=False)
    mc = MinecraftServer()
    sent = []

    async def fake_ssh_run(self, cmd, timeout=30, input_text=None):
        sent.append(cmd)
        return (self.service_name not in fail), ""

    fail = set()
    monkeypatch.setattr("gamefunc.compose_server.DockerComposeGameServer._ssh_run", fake_ssh_run)
    return mc, sent, fail


async def test_start_brings_up_backend_then_proxy(server):
    mc, sent, _ = server
    assert await mc.start("vanilla") is True
    assert sent == ["cd /home/data && docker compose up -d minecraft",
                    "cd /home/data && docker compose up -d mc-proxy"]


async def test_proxy_failure_fails_start(server):
    mc, _, fail = server
    fail.add("mc-proxy")
    assert await mc.start("vanilla") is False


async def test_backend_failure_skips_proxy(server):
    mc, sent, fail = server
    fail.add("minecraft")
    assert await mc.start("vanilla") is False
    assert sent == ["cd /home/data && docker compose up -d minecraft"]


async def test_proxy_can_be_disabled(server, monkeypatch):
    mc, sent, _ = server
    monkeypatch.setenv("MINECRAFT_PROXY_SERVICE", "")
    assert await mc.start("vanilla") is True
    assert sent == ["cd /home/data && docker compose up -d minecraft"]


async def test_proxy_running_checks_proxy_container(server, monkeypatch):
    mc, sent, _ = server
    monkeypatch.setattr("gamefunc.compose_server.DockerComposeGameServer._ssh_run",
                        lambda self, cmd, timeout=30, input_text=None: _ok_true(sent, cmd))
    assert await mc.proxy_running() is True
    assert sent == ["docker inspect -f '{{.State.Running}}' mc-proxy"]


async def test_proxy_running_none_when_disabled(server, monkeypatch):
    mc, _, _ = server
    monkeypatch.setenv("MINECRAFT_PROXY_SERVICE", "")
    assert await mc.proxy_running() is None


async def _ok_true(sent, cmd):
    sent.append(cmd)
    return True, "true"
