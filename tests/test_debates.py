"""chatbotfunc/debates.py scan_channel: structured-output parsing and action application."""

import json
import types

import pytest

import chatbotfunc.debates as debates
import chatbotfunc.utils as utils


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "debates.json"
    monkeypatch.setattr(debates, "_DEBATES_PATH", str(path))
    monkeypatch.setenv("DEBATE_SCAN_MIN_MESSAGES", "1")
    path.write_text(json.dumps({"42": {"last_scan_ts": 1, "next_id": 2, "entries": [{
        "id": 1, "topic": "Trevor's spaghetti belts", "summary": "old", "type": "running_joke",
        "participants": ["Trevor"], "first_seen_ts": 0, "last_mentioned_ts": 0,
        "last_surfaced_ts": 0, "resolved": False,
    }]}}))
    return path


class FakeChannel:
    async def history(self, after, limit, oldest_first):
        for name, text in [("Knova", "pineapple pizza rules"), ("Trevor", "never")]:
            yield types.SimpleNamespace(content=text, author=types.SimpleNamespace(display_name=name))


BOT = types.SimpleNamespace(get_channel=lambda cid: FakeChannel())


def fake_llm(monkeypatch, content, finish_reason="stop"):
    seen = {}

    async def fake(**kw):
        seen.update(kw)
        msg = types.SimpleNamespace(content=content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg, finish_reason=finish_reason)])

    monkeypatch.setattr(utils, "async_chat_completion", fake)
    return seen


async def test_applies_new_update_resolve(store, monkeypatch):
    seen = fake_llm(monkeypatch, json.dumps({"actions": [
        {"action": "new", "id": None, "topic": "Pineapple pizza", "summary": "Unsettled.",
         "type": "unresolved_debate", "participants": ["Knova", "Trevor"]},
        {"action": "update", "id": 1, "topic": None, "summary": "Still spaghetti.",
         "type": None, "participants": None},
        {"action": "resolve", "id": 99, "topic": None, "summary": None, "type": None, "participants": None},
    ]}))
    await debates.scan_channel(BOT, 42, "m")
    ch = json.loads(store.read_text())["42"]
    by_topic = {e["topic"]: e for e in ch["entries"]}
    assert by_topic["Pineapple pizza"]["id"] == 2
    assert by_topic["Pineapple pizza"]["participants"] == ["Knova", "Trevor"]
    assert by_topic["Trevor's spaghetti belts"]["summary"] == "Still spaghetti."
    assert ch["next_id"] == 3
    assert ch["last_scan_ts"] > 1
    assert seen["response_format"]["json_schema"]["strict"] is True


async def test_truncated_response_keeps_scan_window(store, monkeypatch):
    fake_llm(monkeypatch, '{"actions": [{"action": "new", "to', finish_reason="length")
    before = store.read_text()
    await debates.scan_channel(BOT, 42, "m")
    assert store.read_text() == before  # nothing applied, last_scan_ts not advanced
