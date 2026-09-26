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
    monkeypatch.delenv("IMAGE_SIZE", raising=False)
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
    chat, image, size = view.children
    assert [o.value for o in chat.options if o.default] == ["gpt-6-sol"]
    assert [o.value for o in image.options if o.default] == ["gpt-image-2.5-flare"]
    assert image.options[-1].value == "__default__"
    fields = {f.name: f.value for f in build_embed().fields}
    assert "gpt-image-2.5-flare" in fields["Image model"] and "Knova" in fields["Image model"]


def test_image_size_override_and_default():
    assert ms.get_image_size() == "1024x1024"
    ms.set_model("size", "1536x1024", "Knova")
    assert ms.get_image_size() == "1536x1024"
    with pytest.raises(ValueError):
        ms.set_model("size", "4096x4096", "Knova")
    ms.set_model("size", None, "Knova")
    assert ms.get_image_size() == "1024x1024"


@pytest.mark.parametrize("w,h,expected", [
    (1024, 1024, "1024x1024"), (1100, 1000, "1024x1024"),
    (1920, 1080, "1536x1024"), (1080, 1920, "1024x1536"), (0, 0, "1024x1024"),
])
def test_aspect_for_keeps_source_orientation(w, h, expected):
    assert ms.aspect_for(w, h) == expected


def _fake_images(monkeypatch, seen):
    import types
    import AIfunc.responses as responses

    def call(**kw):
        seen.update(kw)
        return types.SimpleNamespace(data=[types.SimpleNamespace(b64_json="aGk=")], usage=None)

    monkeypatch.setattr(responses, "client", types.SimpleNamespace(
        images=types.SimpleNamespace(generate=call, edit=call)))
    monkeypatch.setattr(responses, "record_image", lambda *a: None)
    return responses


async def test_generate_uses_size_setting_unless_overridden(monkeypatch):
    seen = {}
    responses = _fake_images(monkeypatch, seen)
    ms.set_model("size", "1024x1536", "Knova")
    await responses.generate_image("a cat")
    assert seen["size"] == "1024x1536"
    await responses.generate_image("a cat", size=ms.ASPECTS["landscape"])
    assert seen["size"] == "1536x1024"


async def test_transform_follows_source_shape_not_setting(monkeypatch):
    import io
    from PIL import Image
    seen = {}
    responses = _fake_images(monkeypatch, seen)
    ms.set_model("size", "1536x1024", "Knova")
    buf = io.BytesIO()
    Image.new("RGB", (600, 1000)).save(buf, "PNG")
    await responses.transform_image(buf.getvalue(), "add a hat")
    assert seen["size"] == "1024x1536"


def test_generate_tool_offers_exactly_the_aspects():
    from cogs.chat_tools import GENERATE_TOOL
    aspect = GENERATE_TOOL["function"]["parameters"]["properties"]["aspect"]
    assert set(aspect["enum"]) == set(ms.ASPECTS)
    assert "aspect" not in GENERATE_TOOL["function"]["parameters"]["required"]
