import chromadb
import asyncio
import time
import os
import re

# ChromaDB persists to disk here — survives bot restarts
_DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'chroma')

# How many chunks to retrieve per query
RETRIEVAL_K = 5

# How many recent messages to always keep in direct context (recency still matters)
RECENT_CONTEXT_MESSAGES = 6

# Maximum characters per document chunk
CHUNK_SIZE = 3000
CHUNK_OVERLAP = 300

# Cosine distance threshold for retrieval (0=identical, 1=unrelated, 2=opposite)
# Results above this value are dropped as too dissimilar to the query
DISTANCE_THRESHOLD = 0.8

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


def _get_client():
    os.makedirs(os.path.abspath(_DB_PATH), exist_ok=True)
    return chromadb.PersistentClient(path=os.path.abspath(_DB_PATH))


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

    def store_message(self, role: str, content: str, message_id: int = None):
        """Store a single Discord message. Skips empty or low-value content."""
        if not content or not content.strip():
            return
        # Always store bot responses; filter junk from user messages
        if role != "assistant" and not _should_store(content):
            return
        doc_id = f"msg-{message_id}" if message_id else f"msg-{int(time.time() * 1000)}"
        try:
            self._col.upsert(
                ids=[doc_id],
                documents=[f"{role}: {content}"],
                metadatas=[{"type": "message", "role": role, "ts": int(time.time())}],
            )
        except Exception as e:
            print(f"[memory] store_message error: {e}")

    def store_document(self, text: str, source: str = "upload"):
        """Chunk and store a document. Returns number of chunks stored."""
        chunks = _chunk_text(text)
        ids, docs, metas = [], [], []
        base_ts = int(time.time() * 1000)
        for i, chunk in enumerate(chunks):
            ids.append(f"doc-{base_ts}-{i}")
            docs.append(chunk)
            metas.append({"type": "document", "source": source, "ts": int(time.time())})
        if ids:
            try:
                self._col.upsert(ids=ids, documents=docs, metadatas=metas)
            except Exception as e:
                print(f"[memory] store_document error: {e}")
        return len(chunks)

    # ── Reading ───────────────────────────────────────────────────────────────

    def retrieve(self, query: str, k: int = RETRIEVAL_K, doc_type: str = None) -> list[str]:
        """Return document chunks relevant to query, filtered by distance threshold."""
        count = self._col.count()
        if count == 0:
            return []
        k = min(k, count)
        where = {"type": doc_type} if doc_type else None
        try:
            results = self._col.query(
                query_texts=[query],
                n_results=k,
                where=where,
                include=["documents", "distances"],
            )
            docs = results["documents"][0] if results["documents"] else []
            distances = results["distances"][0] if results["distances"] else []
            return [doc for doc, dist in zip(docs, distances) if dist <= DISTANCE_THRESHOLD]
        except Exception as e:
            print(f"[memory] retrieve error: {e}")
            return []

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
        except Exception as e:
            print(f"[memory] clear_documents error: {e}")
        return 0

    def clear_all(self):
        """Wipe everything for this channel."""
        try:
            self._client.delete_collection(_collection_name(self.channel_id))
            self._col = self._client.get_or_create_collection(
                name=_collection_name(self.channel_id),
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:
            print(f"[memory] clear_all error: {e}")


# ── Async helpers (run DB ops in thread so they don't block the event loop) ──

async def async_store_message(channel_id: int, role: str, content: str, message_id: int = None):
    mem = ChannelMemory(channel_id)
    await asyncio.to_thread(mem.store_message, role, content, message_id)


async def async_store_document(channel_id: int, text: str, source: str = "upload") -> int:
    mem = ChannelMemory(channel_id)
    return await asyncio.to_thread(mem.store_document, text, source)


async def async_retrieve(channel_id: int, query: str, k: int = RETRIEVAL_K, doc_type: str = None) -> list[str]:
    mem = ChannelMemory(channel_id)
    return await asyncio.to_thread(mem.retrieve, query, k, doc_type)


async def async_count(channel_id: int) -> dict:
    mem = ChannelMemory(channel_id)
    return await asyncio.to_thread(mem.count)


async def async_clear_documents(channel_id: int) -> int:
    mem = ChannelMemory(channel_id)
    return await asyncio.to_thread(mem.clear_documents)


async def async_clear_all(channel_id: int):
    mem = ChannelMemory(channel_id)
    await asyncio.to_thread(mem.clear_all)
