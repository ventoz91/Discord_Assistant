"""chatbotfunc/model_settings.py + cogs/models.py: runtime model overrides."""

import json

import pytest

import chatbotfunc.model_settings as ms


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    path = tmp_path / "model_settings.json"
    monkeypatch.setattr(ms, "_PATH", str(path))
    monkeypatch.setenv("MODEL_CHAT", "gpt-6-sol")
    monkeypatch.delenv("IMAGE_MODEL", raising=False)
    return path


def test_defaults_come_from_env():
    assert ms.get_chat_model() == "gpt-6-sol"
    assert ms.get_image_model() == "gpt-image-1"  # built-in fallback


def test_override_wins_and_persists(store):
    ms.set_model("chat", "gpt-6-luna", "Knova")
    assert ms.get_chat_model() == "gpt-6-luna"
    saved = json.loads(store.read_text())
    assert saved["chat"]["model"] == "gpt-6-luna" and saved["chat"]["set_by"] == "Knova"
    assert ms.get_image_model() == "gpt-image-1"  # other kind untouched


def test_clear_returns_to_env_default():
    ms.set_model("image", "gpt-image-1-mini", "Knova")
    ms.set_model("image", None, "Knova")
    assert ms.get_image_model() == "gpt-image-1"


def test_rejects_models_outside_curated_list():
    with pytest.raises(ValueError):
        ms.set_model("chat", "gpt-6-astra", "Knova")


def test_stale_override_is_ignored(store):
    store.write_text(json.dumps({"chat": {"model": "gpt-4o", "set_by": "x", "ts": 0}}))
    assert ms.get_chat_model() == "gpt-6-sol"


def test_generate_gpt_response_uses_switched_model(monkeypatch):
    import asyncio
    import types
    import AIfunc.responses as responses

    seen = {}

    async def fake(**kw):
        seen.update(kw)
        msg = types.SimpleNamespace(content="hi", tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr(responses, "async_chat_completion", fake)
    ms.set_model("chat", "gpt-6-luna", "Knova")
    asyncio.run(responses.generate_gpt_response([], "a dwarf"))
    assert seen["model"] == "gpt-6-luna"


async def test_picker_marks_current_and_offers_default():
    from cogs.models import ModelView, build_embed
    ms.set_model("image", "gpt-image-2.5-flare", "Knova")
    view = ModelView()
    chat, image = view.children
    assert [o.value for o in chat.options if o.default] == ["gpt-6-sol"]
    assert [o.value for o in image.options if o.default] == ["gpt-image-2.5-flare"]
    assert image.options[-1].value == "__default__"
    fields = {f.name: f.value for f in build_embed().fields}
    assert "gpt-image-2.5-flare" in fields["Image model"] and "Knova" in fields["Image model"]
