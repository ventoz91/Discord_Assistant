import time
import types

from ragfunc.memory import ChannelMemory, _should_store, _chunk_text, CHUNK_SIZE


class FakeCol:
    def __init__(self, query_result=None):
        self.upserts = []
        self._query_result = query_result

    def upsert(self, ids, documents, metadatas):
        self.upserts.append((ids, documents, metadatas))

    def count(self):
        return 100

    def query(self, **kwargs):
        return self._query_result


def mem_with(col):
    return types.SimpleNamespace(_col=col)


class TestShouldStore:
    def test_filler_dropped(self):
        for phrase in ("lol", "ok", "nice.", "gg"):
            assert not _should_store(phrase)

    def test_short_dropped(self):
        assert not _should_store("hi")

    def test_url_only_dropped(self):
        assert not _should_store("https://tenor.com/view/thing-123")

    def test_mention_only_dropped(self):
        assert not _should_store("<@1234567890>")

    def test_real_content_kept(self):
        assert _should_store("I main engineer in Deep Rock Galactic")


class TestStoreMessage:
    def test_author_prefixed_after_filters(self):
        col = FakeCol()
        ChannelMemory.store_message(mem_with(col), "user", "I main engineer in DRG", 1, None, "Knova")
        assert col.upserts[0][1] == ["user: Knova: I main engineer in DRG"]

    def test_filler_dropped_despite_long_author_name(self):
        col = FakeCol()
        ChannelMemory.store_message(mem_with(col), "user", "lol", 2, None, "Melissaisamom")
        assert col.upserts == []

    def test_short_assistant_reply_dropped(self):
        col = FakeCol()
        ChannelMemory.store_message(mem_with(col), "assistant", "Got it, will do!", 3, None, None)
        assert col.upserts == []

    def test_context_snippet_in_metadata(self):
        col = FakeCol()
        ChannelMemory.store_message(mem_with(col), "user", "a genuinely long enough message", 4, "previous context", "A")
        assert col.upserts[0][2][0]["ctx"] == "previous context"


class TestChunkText:
    def test_short_text_single_chunk(self):
        assert _chunk_text("hello") == ["hello"]

    def test_long_text_overlapping_chunks(self):
        text = ("Sentence one. " * 400)
        chunks = _chunk_text(text)
        assert len(chunks) > 1
        assert all(len(c) <= CHUNK_SIZE for c in chunks)


def _query_result(entries):
    """entries: list of (doc, distance, meta)"""
    return {
        "documents": [[e[0] for e in entries]],
        "distances": [[e[1] for e in entries]],
        "metadatas": [[e[2] for e in entries]],
    }


class TestRetrieve:
    def test_expired_entries_skipped(self):
        now = int(time.time())
        col = FakeCol(_query_result([
            ("fresh", 0.3, {"type": "message", "ts": now, "expires_at": now + 1000}),
            ("expired", 0.1, {"type": "message", "ts": now, "expires_at": now - 10}),
        ]))
        got = ChannelMemory.retrieve(mem_with(col), "query")
        assert got == ["fresh"]

    def test_decay_pushes_old_messages_over_threshold(self):
        now = int(time.time())
        old_ts = now - 28 * 86400  # two half-lives at default 14d -> distance x4
        col = FakeCol(_query_result([
            ("old borderline", 0.5, {"type": "message", "ts": old_ts, "expires_at": now + 1000}),
            ("new borderline", 0.5, {"type": "message", "ts": now, "expires_at": now + 1000}),
        ]))
        got = ChannelMemory.retrieve(mem_with(col), "query")
        assert got == ["new borderline"]  # 0.5 passes at 0.8; old effective 2.0 fails

    def test_documents_never_decayed(self):
        now = int(time.time())
        old_ts = now - 365 * 86400
        col = FakeCol(_query_result([
            ("ancient doc", 0.5, {"type": "document", "ts": old_ts, "expires_at": 0}),
        ]))
        got = ChannelMemory.retrieve(mem_with(col), "query")
        assert got == ["ancient doc"]

    def test_context_snippet_displayed(self):
        now = int(time.time())
        col = FakeCol(_query_result([
            ("the memory", 0.2, {"type": "message", "ts": now, "expires_at": 0, "ctx": "what prompted it"}),
        ]))
        got = ChannelMemory.retrieve(mem_with(col), "query")
        assert got == ["[re: what prompted it]\nthe memory"]

    def test_sorted_by_effective_distance_top_k(self):
        now = int(time.time())
        entries = [(f"doc{i}", 0.1 * i, {"type": "document", "ts": now, "expires_at": 0}) for i in range(6)]
        col = FakeCol(_query_result(entries))
        got = ChannelMemory.retrieve(mem_with(col), "query", k=3)
        assert got == ["doc0", "doc1", "doc2"]
