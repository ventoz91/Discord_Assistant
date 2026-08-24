from __future__ import annotations

import chromadb
import asyncio
import logging
import time
import os
import re

logger = logging.getLogger("bot.memory")

# ChromaDB persists to disk here — survives bot restarts
_DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'chroma')

# How many chunks to retrieve per query
RETRIEVAL_K = 5

# Maximum characters per document chunk
CHUNK_SIZE = 3000
CHUNK_OVERLAP = 300

# DISTANCE_THRESHOLD, MESSAGE_TTL_DAYS, RAG_DECAY_HALFLIFE_DAYS are read from
# .env at call time (see below) rather than cached here, so live edits apply
# without a restart like every other config value in this project.

# Single-word/short filler phrases not worth storing
_FILLER_PHRASES = {
    "lol", "lmao", "lmfao", "haha", "hehe", "ok", "okay", "k", "kk",
    "yes", "no", "yep", "nope", "yeah", "nah", "sure", "true", "false",
    "wow", "oh", "ah", "uh", "um", "hmm", "hm", "wtf", "omg", "gg",
    "nice", "cool", "great", "good", "bad", "same", "rip", "f", "oof",
    "thanks", "ty", "np", "lol.", "ok.", "yeah.", "nah.", "true.", "nice.",
}


def _should_store(content: str) -> bool:
    """Return False for messages too short or low-value to be worth embedding."""
    stripped = content.strip()
    if len(stripped) < 8:
        return False
    # Strip mentions, URLs, emoji markup, punctuation — check what's left
    cleaned = re.sub(r'<[^>]+>', '', stripped)
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = re.sub(r'[^\w\s]', '', cleaned).strip()
    if len(cleaned) < 4:
        return False
    if cleaned.lower() in _FILLER_PHRASES:
        return False
    return True


_client: chromadb.PersistentClient | None = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        os.makedirs(os.path.abspath(_DB_PATH), exist_ok=True)
        _client = chromadb.PersistentClient(path=os.path.abspath(_DB_PATH))
    return _client


def _collection_name(channel_id: int) -> str:
    # ChromaDB collection names must be 3-63 chars, alphanumeric + hyphens
    return f"ch-{channel_id}"


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks suitable for embedding."""
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        # Try to break at a sentence or paragraph boundary
        if end < len(text):
            boundary = max(
                text.rfind('\n', start, end),
                text.rfind('. ', start, end),
                text.rfind('? ', start, end),
                text.rfind('! ', start, end),
            )
            if boundary > start + CHUNK_SIZE // 2:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        start = end - CHUNK_OVERLAP
    return [c for c in chunks if c]


class ChannelMemory:
    """Persistent per-channel memory backed by ChromaDB.

    Two document types are stored:
      - 'message': a Discord message (role + content)
      - 'document': a chunk from an uploaded/learned document
    """

    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        self._client = _get_client()
        self._col = self._client.get_or_create_collection(
            name=_collection_name(channel_id),
            metadata={"hnsw:space": "cosine"},
        )

    # ── Writing ───────────────────────────────────────────────────────────────

    def store_message(self, role: str, content: str, message_id: int = None, context_snippet: str = None, author: str = None):
        """Store a single Discord message. Skips empty or low-value content.

        context_snippet: a short excerpt of the preceding message (≤200 chars),
        stored in metadata and prepended to retrieved results so the model sees
        what prompted each retrieved entry rather than an isolated fragment.

        author: display name of the human speaker; prefixed onto the stored
        content ("Name: message") after the quality filters so name length
        can't sneak filler past them.
        """
        if not content or not content.strip():
            return
        if not _should_store(content):
            return
        # Short bot replies ("Got it", "I'm not sure") aren't worth indexing
        if role == "assistant" and len(content.strip()) < 40:
            return
        if author and role == "user":
            content = f"{author}: {content}"
        doc_id = f"msg-{message_id}" if message_id else f"msg-{int(time.time() * 1000)}"
        message_ttl_days = int(os.getenv("MESSAGE_TTL_DAYS", "30"))
        expires_at = int(time.time()) + message_ttl_days * 86400
        meta = {"type": "message", "role": role, "ts": int(time.time()), "expires_at": expires_at}
        if context_snippet:
            meta["ctx"] = context_snippet[:200]
        try:
            self._col.upsert(
                ids=[doc_id],
                documents=[f"{role}: {content}"],
                metadatas=[meta],
            )
        except Exception:
            logger.exception("store_message failed")

    def store_document(self, text: str, source: str = "upload"):
        """Chunk and store a document. Returns number of chunks stored."""
        chunks = _chunk_text(text)
        ids, docs, metas = [], [], []
        base_ts = int(time.time() * 1000)
        for i, chunk in enumerate(chunks):
            ids.append(f"doc-{base_ts}-{i}")
            docs.append(chunk)
            metas.append({"type": "document", "source": source, "ts": int(time.time()), "expires_at": 0})
        if ids:
            try:
                self._col.upsert(ids=ids, documents=docs, metadatas=metas)
            except Exception:
                logger.exception("store_document failed")
        return len(chunks)

    # ── Reading ───────────────────────────────────────────────────────────────

    def retrieve(self, query: str, k: int = RETRIEVAL_K, doc_type: str = None, before_ts: int = None) -> list[str]:
        """Return document chunks relevant to query, filtered by distance threshold.

        If before_ts is set, only entries stored strictly before that unix
        timestamp are returned. Used to exclude messages already covered by the
        direct-history recency window, so RAG only surfaces older context.

        For message-type entries, applies exponential recency decay: older messages
        need to be proportionally more similar to pass the distance threshold.
        Documents are never decayed. Fetches extra candidates to compensate for
        stricter effective filtering, then re-sorts and returns top k.
        """
        count = self._col.count()
        if count == 0:
            return []
        # Fetch extra candidates so decay filtering doesn't starve the result set
        fetch_k = min(k * 3, count)
        conditions = []
        if doc_type:
            conditions.append({"type": doc_type})
        if before_ts is not None:
            conditions.append({"ts": {"$lt": int(before_ts)}})
        if not conditions:
            where = None
        elif len(conditions) == 1:
            where = conditions[0]
        else:
            where = {"$and": conditions}
        try:
            results = self._col.query(
                query_texts=[query],
                n_results=fetch_k,
                where=where,
                include=["documents", "distances", "metadatas"],
            )
            docs = results["documents"][0] if results["documents"] else []
            distances = results["distances"][0] if results["distances"] else []
            metadatas = results["metadatas"][0] if results["metadatas"] else []
            now = int(time.time())
            halflife = float(os.getenv("RAG_DECAY_HALFLIFE_DAYS", "14"))
            distance_threshold = float(os.getenv("DISTANCE_THRESHOLD", "0.8"))

            scored = []
            for doc, dist, meta in zip(docs, distances, metadatas):
                expires_at = meta.get("expires_at", 0)
                if expires_at != 0 and expires_at <= now:
                    continue
                # Apply recency decay to messages only; documents score as-is
                if halflife > 0 and meta.get("type") == "message":
                    age_days = (now - meta.get("ts", now)) / 86400
                    # adjusted_distance = distance / 2^(-age/halflife)
                    # Old messages appear further away, need higher similarity to survive
                    decay = 2 ** (-age_days / halflife)
                    effective_dist = dist / decay if decay > 0 else float("inf")
                else:
                    effective_dist = dist
                if effective_dist <= distance_threshold:
                    ctx = meta.get("ctx")
                    display = f"[re: {ctx}]\n{doc}" if ctx else doc
                    scored.append((effective_dist, display))

            scored.sort(key=lambda x: x[0])
            return [doc for _, doc in scored[:k]]
        except Exception:
            logger.exception("retrieve failed")
            return []

    def get_by_message_id(self, message_id: int) -> str | None:
        """Look up a stored message entry by its Discord message ID.

        Used to recover the real content behind a placeholder Discord message
        (e.g. a generated image posted as just "Generated Image") when that
        message is still within the raw history window and so wouldn't
        otherwise surface through retrieve()'s before_ts dedup.
        """
        try:
            result = self._col.get(ids=[f"msg-{message_id}"], include=["documents"])
            docs = result.get("documents") or []
            return docs[0] if docs else None
        except Exception:
            logger.exception("get_by_message_id failed")
            return None

    def retrieve_messages(self, query: str, k: int = RETRIEVAL_K) -> list[str]:
        return self.retrieve(query, k=k, doc_type="message")

    def retrieve_documents(self, query: str, k: int = RETRIEVAL_K) -> list[str]:
        return self.retrieve(query, k=k, doc_type="document")

    def count(self) -> dict:
        total = self._col.count()
        return {"total": total}

    def clear_documents(self):
        """Remove all stored documents (not messages) from this channel."""
        try:
            results = self._col.get(where={"type": "document"})
            if results["ids"]:
                self._col.delete(ids=results["ids"])
                return len(results["ids"])
        except Exception:
            logger.exception("clear_documents failed")
        return 0

    def clear_all(self):
        """Wipe everything for this channel."""
        try:
            self._client.delete_collection(_collection_name(self.channel_id))
            self._col = self._client.get_or_create_collection(
                name=_collection_name(self.channel_id),
                metadata={"hnsw:space": "cosine"},
            )
        except Exception:
            logger.exception("clear_all failed")

    def get_expiring(self, before_ts: int) -> tuple[list[str], list[str]]:
        """Return (ids, docs) of message-type entries stored before before_ts."""
        try:
            results = self._col.get(
                where={"$and": [{"type": "message"}, {"ts": {"$lt": int(before_ts)}}]},
                include=["documents"],
            )
            return results.get("ids", []), results.get("documents", [])
        except Exception:
            logger.exception("get_expiring failed")
            return [], []

    def delete_by_ids(self, ids: list[str]):
        """Delete ChromaDB entries by ID."""
        if not ids:
            return
        try:
            self._col.delete(ids=ids)
        except Exception:
            logger.exception("delete_by_ids failed")


def list_channel_ids() -> list[int]:
    """Return all channel IDs that have a ChromaDB collection."""
    try:
        cols = _get_client().list_collections()
        ids = []
        for col in cols:
            name = col.name if hasattr(col, "name") else str(col)
            if name.startswith("ch-"):
                try:
                    ids.append(int(name[3:]))
                except ValueError:
                    pass
        return ids
    except Exception:
        logger.exception("list_channel_ids failed")
        return []


# ── Async helpers (run DB ops in thread so they don't block the event loop) ──

async def async_store_message(channel_id: int, role: str, content: str, message_id: int = None, context_snippet: str = None, author: str = None):
    mem = ChannelMemory(channel_id)
    await asyncio.to_thread(mem.store_message, role, content, message_id, context_snippet, author)


async def async_store_document(channel_id: int, text: str, source: str = "upload") -> int:
    mem = ChannelMemory(channel_id)
    return await asyncio.to_thread(mem.store_document, text, source)


async def async_retrieve(channel_id: int, query: str, k: int = RETRIEVAL_K, doc_type: str = None, before_ts: int = None) -> list[str]:
    mem = ChannelMemory(channel_id)
    return await asyncio.to_thread(mem.retrieve, query, k, doc_type, before_ts)


async def async_get_by_message_id(channel_id: int, message_id: int) -> str | None:
    mem = ChannelMemory(channel_id)
    return await asyncio.to_thread(mem.get_by_message_id, message_id)


async def async_count(channel_id: int) -> dict:
    mem = ChannelMemory(channel_id)
    return await asyncio.to_thread(mem.count)


async def async_clear_documents(channel_id: int) -> int:
    mem = ChannelMemory(channel_id)
    return await asyncio.to_thread(mem.clear_documents)


async def async_clear_all(channel_id: int):
    mem = ChannelMemory(channel_id)
    await asyncio.to_thread(mem.clear_all)
