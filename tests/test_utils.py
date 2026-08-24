import types

from chatbotfunc.utils import describe_extras, fetch_message_history, split_message, IMAGE_EXTENSIONS
from conftest import make_message, FakeChannel


class TestDescribeExtras:
    def test_image_by_extension(self):
        m = make_message(1, "A", "", attachments=("cat.png",))
        assert describe_extras(m) == "[shared image: cat.png]"

    def test_image_by_mime_with_weird_name(self):
        m = make_message(1, "A", "", attachments=("weird_name",), content_types=("image/gif",))
        assert describe_extras(m) == "[shared image: weird_name]"

    def test_video_by_mime(self):
        m = make_message(1, "A", "", attachments=("fake_gif.mp4",), content_types=("video/mp4",))
        assert describe_extras(m) == "[shared video: fake_gif.mp4]"

    def test_generic_file(self):
        m = make_message(1, "A", "", attachments=("notes.pdf",))
        assert describe_extras(m) == "[shared file: notes.pdf]"

    def test_sticker(self):
        m = make_message(1, "A", "", stickers=("wave",))
        assert describe_extras(m) == "[sticker: wave]"

    def test_empty(self):
        assert describe_extras(make_message(1, "A", "hi")) == ""


class TestFetchMessageHistory:
    async def test_attribution_and_placeholders(self, bot):
        msgs = [  # newest first
            make_message(3, "Ventoz", "why only my gifs?"),
            make_message(2, None, "Splungis approves.", is_bot=True),
            make_message(1, "Knova", "", attachments=("cat.gif",)),
        ]
        hist = await fetch_message_history(FakeChannel(msgs), bot)
        assert hist == [
            {"role": "user", "content": "Knova: [shared image: cat.gif]"},
            {"role": "assistant", "content": "Splungis approves."},
            {"role": "user", "content": "Ventoz: why only my gifs?"},
        ]

    async def test_empty_messages_skipped(self, bot):
        msgs = [make_message(2, "A", "hello"), make_message(1, "B", "")]
        hist = await fetch_message_history(FakeChannel(msgs), bot)
        assert len(hist) == 1

    async def test_exclude_message_id(self, bot):
        msgs = [make_message(2, "A", "current"), make_message(1, "B", "older")]
        hist = await fetch_message_history(FakeChannel(msgs), bot, exclude_message_id=2)
        assert hist == [{"role": "user", "content": "B: older"}]

    async def test_cutoff_is_oldest_kept_message(self, bot):
        msgs = [make_message(2, "A", "new"), make_message(1, "B", "old")]
        hist, cutoff = await fetch_message_history(FakeChannel(msgs), bot, return_cutoff=True)
        assert cutoff == int(msgs[-1].created_at.timestamp())

    async def test_respects_history_length(self, bot, monkeypatch):
        monkeypatch.setenv("HISTORYLENGTH", "2")
        msgs = [make_message(i, "A", f"msg {i}") for i in range(5, 0, -1)]
        hist = await fetch_message_history(FakeChannel(msgs), bot)
        assert len(hist) == 2
        assert hist[-1]["content"] == "A: msg 5"  # newest kept

    async def test_generated_image_placeholder_recovers_stored_prompt(self, bot, monkeypatch):
        async def fake_lookup(channel_id, message_id):
            assert (channel_id, message_id) == (42, 1)
            return "assistant: [generated image for prompt: a poster about trash cans]"

        monkeypatch.setattr("chatbotfunc.utils.async_get_by_message_id", fake_lookup)
        msgs = [make_message(1, None, "Generated Image", is_bot=True)]
        hist = await fetch_message_history(FakeChannel(msgs, channel_id=42), bot)
        assert hist == [{"role": "assistant", "content": "[generated image for prompt: a poster about trash cans]"}]

    async def test_generated_image_placeholder_falls_back_when_not_stored(self, bot, monkeypatch):
        async def fake_lookup(channel_id, message_id):
            return None

        monkeypatch.setattr("chatbotfunc.utils.async_get_by_message_id", fake_lookup)
        msgs = [make_message(1, None, "Generated Image", is_bot=True)]
        hist = await fetch_message_history(FakeChannel(msgs), bot)
        assert hist == [{"role": "assistant", "content": "Generated Image"}]

    async def test_normal_bot_reply_skips_lookup(self, bot, monkeypatch):
        def fail(*args, **kwargs):
            raise AssertionError("should not look up ordinary bot replies")

        monkeypatch.setattr("chatbotfunc.utils.async_get_by_message_id", fail)
        msgs = [make_message(1, None, "just a normal reply", is_bot=True)]
        hist = await fetch_message_history(FakeChannel(msgs), bot)
        assert hist == [{"role": "assistant", "content": "just a normal reply"}]


class TestSplitMessage:
    def test_short_message_untouched(self):
        assert split_message("hello") == ["hello"]

    def test_long_message_chunks_under_limit(self):
        text = "word " * 1000
        chunks = split_message(text)
        assert len(chunks) > 1
        assert all(len(c) <= 2000 for c in chunks)

    def test_empty_returns_no_chunks(self):
        assert split_message("   ") == []
