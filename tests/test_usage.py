"""chatbotfunc/usage.py: cost recording and summaries (store isolated by conftest)."""

import types

import pytest

import chatbotfunc.usage as usage


def chat_usage(prompt, completion, cached=0):
    return types.SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                                 prompt_tokens_details=types.SimpleNamespace(cached_tokens=cached))


def test_chat_cost_uses_cached_rate():
    usage.record_chat("gpt-6-sol", chat_usage(1_000_000, 100_000, cached=400_000), "chat")
    s = usage.summarize(1)
    # 600k uncached * $2 + 400k cached * $0.20 + 100k out * $10 = 1.20 + 0.08 + 1.00
    assert s["cost"] == pytest.approx(2.28)
    assert s["calls"] == 1 and s["by_feature"] == {"chat": pytest.approx(2.28)}


def test_dated_snapshot_priced_like_base_and_features_split():
    usage.record_chat("gpt-6-luna", chat_usage(1_000_000, 0), "profiles")
    usage.record_chat("gpt-5.4-2026-03-05", chat_usage(1_000_000, 0), "chat")
    s = usage.summarize(30)
    assert s["by_feature"]["profiles"] == pytest.approx(0.10)
    assert s["by_model"]["gpt-5.4-2026-03-05"] == pytest.approx(2.50)
    assert s["unpriced"] == 0


def test_image_cost_from_measured_usage():
    # Real gpt-image-1-mini edit usage measured 2026-09-25.
    u = types.SimpleNamespace(input_tokens=1034, output_tokens=272,
                              input_tokens_details=types.SimpleNamespace(image_tokens=1024, text_tokens=10))
    usage.record_image("gpt-image-1-mini", u, "images")
    s = usage.summarize(1)
    assert s["images"] == 1
    assert s["cost"] == pytest.approx((10 * 2.00 + 1024 * 2.50 + 272 * 8.00) / 1e6)


def test_unknown_model_counted_without_cost():
    usage.record_chat("some-future-model", chat_usage(500, 50), "chat")
    s = usage.summarize(1)
    assert s["calls"] == 1 and s["cost"] == 0 and s["unpriced"] == 1


def test_none_usage_is_ignored():
    usage.record_chat("gpt-6-sol", None, "chat")
    assert usage.summarize(1)["calls"] == 0


async def test_wrapper_records_with_tag(monkeypatch):
    import chatbotfunc.utils as utils
    resp = types.SimpleNamespace(usage=chat_usage(1000, 10))
    monkeypatch.setattr(utils.openai.chat.completions, "create", lambda **kw: resp)
    await utils.async_chat_completion(model="gpt-6-luna", messages=[], usage_tag="debates")
    assert "debates" in usage.summarize(1)["by_feature"]


def test_usage_embed_renders():
    from cogs.models import build_usage_embed
    usage.record_chat("gpt-6-sol", chat_usage(10_000, 500), "chat")
    embed = build_usage_embed()
    names = [f.name for f in embed.fields]
    assert names[:3] == ["Today", "Last 7 days", "Last 30 days"]
    assert "gpt-6-sol" in embed.fields[4].value
