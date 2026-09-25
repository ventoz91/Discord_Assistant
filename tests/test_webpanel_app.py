import pytest
from fastapi.testclient import TestClient

import webpanel.auth as auth
import webpanel.routes_servers as rs
from webpanel.app import create_app
from webpanel.auth import hash_password


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBPANEL_SECRET_KEY", "test-secret-key")
    auth._failed_logins.clear()
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


def test_repeated_failures_lock_out_even_correct_password(client):
    for _ in range(auth._MAX_FAILED_LOGINS):
        assert client.post("/login", data={"username": "trevor", "password": "wrong"}).status_code == 401
    resp = client.post("/login", data={"username": "trevor", "password": "hunter2"}, follow_redirects=False)
    assert resp.status_code == 429
    assert "Too many failed attempts" in resp.text


def test_lockout_expires_after_window(client, monkeypatch):
    for _ in range(auth._MAX_FAILED_LOGINS):
        client.post("/login", data={"username": "trevor", "password": "wrong"})
    real_time = auth.time.time
    monkeypatch.setattr(auth.time, "time", lambda: real_time() + auth._FAILED_LOGIN_WINDOW + 1)
    resp = client.post("/login", data={"username": "trevor", "password": "hunter2"}, follow_redirects=False)
    assert resp.status_code == 303


def test_success_clears_failure_count(client):
    for _ in range(auth._MAX_FAILED_LOGINS - 1):
        client.post("/login", data={"username": "trevor", "password": "wrong"})
    client.post("/login", data={"username": "trevor", "password": "hunter2"})
    client.get("/logout")
    for _ in range(auth._MAX_FAILED_LOGINS - 1):
        assert client.post("/login", data={"username": "trevor", "password": "wrong"}).status_code == 401


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


def test_dashboard_lists_current_servers(client):
    client.post("/login", data={"username": "trevor", "password": "hunter2"})
    text = client.get("/").text
    for label in ("Minecraft — Modded", "RuneScape: Dragonwilds", "Palworld"):
        assert label in text
    for gone in ("Valheim", "Enshrouded"):
        assert gone not in text


async def test_dragonwilds_status_start_stop(monkeypatch):
    calls = []

    class FakeDW:
        async def is_running(self): return True
        async def start(self): calls.append("start"); return True
        async def stop(self): calls.append("stop"); return True

    monkeypatch.setattr(rs, "_dw", FakeDW())
    monkeypatch.setenv("DRAGONWILDS_CONNECT_URL", "10.0.0.2:7778")
    entry = rs._find("dragonwilds")
    status = await rs._status(entry)
    assert status["online"] is True and status["connect"] == "10.0.0.2:7778"
    assert status["redeployable"] is False
    assert await rs._start(entry) == "Start requested."
    assert await rs._stop(entry) == "Stop requested."
    assert calls == ["start", "stop"]
