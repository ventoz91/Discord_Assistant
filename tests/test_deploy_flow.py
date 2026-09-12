import pytest
from fastapi.testclient import TestClient

import webpanel.routes_servers as rs
import webpanel.store as store
from gamefunc.compose_server import DockerComposeGameServer
from webpanel.app import create_app
from webpanel.auth import hash_password


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBPANEL_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("WEBPANEL_USERNAME", "trevor")
    monkeypatch.setenv("WEBPANEL_PASSWORD_HASH", hash_password("hunter2"))
    monkeypatch.setenv("DEPLOY_TARGET_HOST", "10.13.37.102")
    monkeypatch.setenv("DEPLOY_TARGET_USER", "admin")
    monkeypatch.setattr(store, "_STORE_PATH", str(tmp_path / "deployed_servers.json"))

    # No real SSH/network in tests — fake every DockerComposeGameServer verb
    # that would otherwise shell out.
    async def fake_write_file(self, remote_path, content, timeout=15):
        return True

    async def fake_start(self):
        return True

    async def fake_down(self):
        return True

    async def fake_run(self, remote_cmd, timeout=15):
        return True, ""  # empty `ss -tuln` output — no ports ever "in use"

    monkeypatch.setattr(DockerComposeGameServer, "write_file", fake_write_file)
    monkeypatch.setattr(DockerComposeGameServer, "start", fake_start)
    monkeypatch.setattr(DockerComposeGameServer, "down", fake_down)
    monkeypatch.setattr(DockerComposeGameServer, "run", fake_run)

    async def fake_status(entry):
        return {**entry, "online": None, "detail": "", "connect": "", "redeployable": False,
                "deletable": False, "base_url": f"/servers/{entry['id']}"}
    monkeypatch.setattr(rs, "_status", fake_status)

    c = TestClient(create_app(bot=None))
    c.post("/login", data={"username": "trevor", "password": "hunter2"})
    return c


def test_deploy_custom_template_end_to_end(client):
    resp = client.post("/deploy/custom", data={
        "name": "myzomboid",
        "image": "someimage:latest",
        "ports": "16261:16261/udp",
        "env": "SERVER_NAME=Test\nADMIN_PASSWORD=secret",
        "volume_path": "/server-data",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"

    inst = store.get_instance("myzomboid")
    assert inst is not None
    assert inst["image"] == "someimage:latest"
    assert inst["ports"] == [{"host_port": 16261, "container_port": 16261, "protocol": "udp"}]


def test_deploy_rejects_bad_name(client):
    resp = client.post("/deploy/custom", data={
        "name": "Not Valid!", "image": "img", "ports": "1:1/tcp", "env": "",
    })
    assert resp.status_code == 400
    assert store.get_instance("Not Valid!") is None


def test_deploy_rejects_duplicate_name(client):
    client.post("/deploy/custom", data={"name": "dupe", "image": "img", "ports": "1:1/tcp", "env": ""})
    resp = client.post("/deploy/custom", data={"name": "dupe", "image": "img2", "ports": "2:2/tcp", "env": ""})
    assert resp.status_code == 400


def test_deploy_rejects_reserved_name(client):
    resp = client.post("/deploy/custom", data={
        "name": "satisfactory", "image": "img", "ports": "1:1/tcp", "env": "",
    })
    assert resp.status_code == 400
    assert store.get_instance("satisfactory") is None


def test_deploy_rejects_bad_port_line(client):
    resp = client.post("/deploy/custom", data={
        "name": "badports", "image": "img", "ports": "not-a-port", "env": "",
    })
    assert resp.status_code == 400
    assert store.get_instance("badports") is None


def test_deploy_terraria_curated_template(client):
    resp = client.post("/deploy/terraria", data={
        "name": "terraria-1", "port_0": "7777", "WORLD": "myworld", "DIFFICULTY": "1", "MAXPLAYERS": "8",
    }, follow_redirects=False)
    assert resp.status_code == 303
    inst = store.get_instance("terraria-1")
    assert inst["template"] == "terraria"
    assert inst["ports"][0]["container_port"] == 7777


def test_deployed_delete_requires_matching_confirmation(client):
    client.post("/deploy/custom", data={"name": "todelete", "image": "img", "ports": "1:1/tcp", "env": ""})

    resp = client.post("/deployed/todelete/delete", data={"confirm_name": "wrong"})
    assert resp.status_code == 400
    assert store.get_instance("todelete") is not None

    resp = client.post("/deployed/todelete/delete", data={"confirm_name": "todelete"}, follow_redirects=False)
    assert resp.status_code == 303
    assert store.get_instance("todelete") is None
