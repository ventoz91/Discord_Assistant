import time
import types

import pytest

import cogs.chat as chat


class BoomTyping:
    async def __aenter__(self):
        raise RuntimeError("500 Internal Server Error")

    async def __aexit__(self, *a):
        return False


class OkTyping:
    def __init__(self):
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True

    async def __aexit__(self, *a):
        self.exited = True
        return False


class Chan:
    def __init__(self, cid, typing_cm=None, send_fails=False):
        self.id = cid
        self._typing_cm = typing_cm
        self.send_fails = send_fails
        self.sent = []

    def typing(self):
        return self._typing_cm or OkTyping()

    async def send(self, content):
        if self.send_fails:
            raise RuntimeError("send 500")
        self.sent.append(content)


@pytest.fixture(autouse=True)
def clean_degradation_state():
    chat._api_failure_ts.clear()
    chat._api_warned_ts.clear()
    yield
    chat._api_failure_ts.clear()
    chat._api_warned_ts.clear()


class TestSafeTyping:
    async def test_body_runs_when_typing_fails(self):
        ran = False
        async with chat._safe_typing(Chan(1, BoomTyping())):
            ran = True
        assert ran

    async def test_failure_marks_channel_degraded(self):
        async with chat._safe_typing(Chan(42, BoomTyping())):
            pass
        assert 42 in chat._api_failure_ts

    async def test_happy_path_enters_and_exits(self):
        cm = OkTyping()
        async with chat._safe_typing(Chan(1, cm)):
            pass
        assert cm.entered and cm.exited

    async def test_body_exception_propagates(self):
        with pytest.raises(ValueError):
            async with chat._safe_typing(Chan(1)):
                raise ValueError("body error")


class TestDegradationNotice:
    async def test_fires_once_then_cooldown(self):
        ch = Chan(1)
        chat._api_failure_ts[1] = time.time()
        await chat._maybe_send_degradation_notice(ch)
        await chat._maybe_send_degradation_notice(ch)
        assert len(ch.sent) == 1

    async def test_silent_without_recent_failure(self):
        ch = Chan(2)
        await chat._maybe_send_degradation_notice(ch)
        assert ch.sent == []

    async def test_silent_when_failure_stale(self):
        ch = Chan(3)
        chat._api_failure_ts[3] = time.time() - chat._API_DEGRADED_WINDOW - 60
        await chat._maybe_send_degradation_notice(ch)
        assert ch.sent == []

    async def test_failed_notice_swallowed_and_cooldown_not_stamped(self):
        ch = Chan(4, send_fails=True)
        chat._api_failure_ts[4] = time.time()
        await chat._maybe_send_degradation_notice(ch)
        assert 4 not in chat._api_warned_ts


class TestIsLoneUrl:
    def test_bare_url(self):
        assert chat._is_lone_url("https://tenor.com/view/cow-gif-123")

    def test_url_with_text(self):
        assert not chat._is_lone_url("look at this https://tenor.com/x")

    def test_empty_and_none(self):
        assert not chat._is_lone_url("")
        assert not chat._is_lone_url(None)


class RefetchChan:
    def __init__(self, refreshed):
        self._refreshed = refreshed

    async def fetch_message(self, mid):
        return self._refreshed


def make_embed(thumb_url, page_url="https://tenor.com/view/x"):
    return types.SimpleNamespace(
        url=page_url,
        image=None,
        thumbnail=types.SimpleNamespace(url=thumb_url),
    )


class TestEmbedImageSource:
    async def test_immediate_embed_no_wait(self):
        msg = types.SimpleNamespace(id=1, embeds=[make_embed("https://media.tenor.com/p.gif")], channel=None)
        t0 = time.monotonic()
        url, label = await chat.ChatCog._embed_image_source(None, msg)
        assert url == "https://media.tenor.com/p.gif"
        assert label == "https://tenor.com/view/x"
        assert time.monotonic() - t0 < 1

    async def test_late_embed_found_via_refetch(self):
        refreshed = types.SimpleNamespace(embeds=[make_embed("https://media.tenor.com/late.gif")])
        msg = types.SimpleNamespace(id=1, embeds=[], channel=RefetchChan(refreshed))
        url, _ = await chat.ChatCog._embed_image_source(None, msg)
        assert url == "https://media.tenor.com/late.gif"

    async def test_no_embed_returns_none(self):
        refreshed = types.SimpleNamespace(embeds=[])
        msg = types.SimpleNamespace(id=1, embeds=[], channel=RefetchChan(refreshed))
        assert await chat.ChatCog._embed_image_source(None, msg) == (None, None)
