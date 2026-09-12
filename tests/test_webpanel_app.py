import pytest
from fastapi.testclient import TestClient

import webpanel.routes_servers as rs
from webpanel.app import create_app
from webpanel.auth import hash_password


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBPANEL_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("WEBPANEL_USERNAME", "trevor")
    monkeypatch.setenv("WEBPANEL_PASSWORD_HASH", hash_password("hunter2"))
    # Dashboard status checks would otherwise attempt real SSH/RCON/network
    # calls — stub with a fake so these tests stay pure-logic.
    async def fake_status(entry):
        return {**entry, "online": None, "detail": "", "connect": "", "redeployable": False,
                "deletable": False, "base_url": f"/servers/{entry['id']}"}
    monkeypatch.setattr(rs, "_status", fake_status)
    return TestClient(create_app(bot=None))


def test_root_redirects_to_login_when_unauthenticated(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_login_page_loads(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Password" in resp.text


def test_wrong_password_rejected(client):
    resp = client.post("/login", data={"username": "trevor", "password": "wrong"})
    assert resp.status_code == 401


def test_correct_login_reaches_dashboard(client):
    resp = client.post("/login", data={"username": "trevor", "password": "hunter2"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"

    resp = client.get("/")
    assert resp.status_code == 200
    assert "Game Servers" in resp.text


def test_logout_requires_login_again(client):
    client.post("/login", data={"username": "trevor", "password": "hunter2"})
    client.get("/logout")
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
