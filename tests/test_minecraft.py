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


async def test_modded_start_uses_systemd_not_compose(monkeypatch):
    mc = MinecraftServer()
    calls = []

    async def fake_start(self):
        calls.append(self.unit())
        return True

    async def no_compose(self, cmd, timeout=30, input_text=None):
        raise AssertionError("modded must not touch docker compose")

    monkeypatch.setattr("gamefunc.user_service.RemoteUserService.start", fake_start)
    monkeypatch.setattr("gamefunc.compose_server.DockerComposeGameServer._ssh_run", no_compose)
    assert await mc.start("modded") is True
    assert calls == ["minecraft-modded"]


async def test_modded_has_no_proxy():
    assert await MinecraftServer().proxy_running("modded") is None


async def test_modded_stop_falls_back_to_systemd_when_rcon_down(monkeypatch):
    monkeypatch.setenv("MINECRAFT_MODDED_SSH_HOST", "10.0.0.5")
    mc = MinecraftServer()

    async def rcon_down(server_type, command):
        raise ConnectionRefusedError("rcon down")

    async def fake_stop(self):
        return True

    monkeypatch.setattr(mc, "_rcon", rcon_down)
    monkeypatch.setattr("gamefunc.user_service.RemoteUserService.stop", fake_stop)
    assert await mc.stop("modded") == "Stopped via systemd."


async def test_modded_stop_saves_via_rcon_then_reaps_unit(monkeypatch):
    monkeypatch.setenv("MINECRAFT_MODDED_SSH_HOST", "10.0.0.5")
    mc = MinecraftServer()
    order = []

    async def rcon(server_type, command):
        order.append(f"rcon {command}")
        return "Stopping the server"

    async def stopped(server_type, timeout=60):
        order.append("wait rcon down")
        return True

    async def unit_stop(self):
        order.append("systemctl stop")
        return True

    monkeypatch.setattr(mc, "_rcon", rcon)
    monkeypatch.setattr(mc, "wait_until_stopped", stopped)
    monkeypatch.setattr("gamefunc.user_service.RemoteUserService.stop", unit_stop)
    assert await mc.stop("modded") == "Stopping the server"
    assert order == ["rcon stop", "wait rcon down", "systemctl stop"]


async def test_vanilla_stop_is_rcon_only(monkeypatch):
    mc = MinecraftServer()
    calls = []

    async def rcon(server_type, command):
        calls.append(server_type)
        return "ok"

    async def unit_stop(self):
        raise AssertionError("vanilla must not touch systemd")

    monkeypatch.setattr(mc, "_rcon", rcon)
    monkeypatch.setattr("gamefunc.user_service.RemoteUserService.stop", unit_stop)
    assert await mc.stop("vanilla") == "ok" and calls == ["vanilla"]
