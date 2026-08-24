import os
import sys
import types
import datetime

# Modules under test read env at import (responses.py raises without a key)
os.environ.setdefault("OPENAI_API_KEY", "test-dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


BOT_USER = object()


@pytest.fixture
def bot():
    return types.SimpleNamespace(user=BOT_USER)


def make_message(mid, author_name, content, attachments=(), stickers=(), is_bot=False,
                 content_types=None):
    """Build a fake Discord message. attachments: filenames; content_types: parallel MIME list."""
    content_types = content_types or [None] * len(attachments)
    return types.SimpleNamespace(
        id=mid,
        author=BOT_USER if is_bot else types.SimpleNamespace(display_name=author_name),
        content=content,
        attachments=[types.SimpleNamespace(filename=f, content_type=ct)
                     for f, ct in zip(attachments, content_types)],
        stickers=[types.SimpleNamespace(name=s) for s in stickers],
        created_at=datetime.datetime(2026, 7, 17, 3, 0, min(mid, 59), tzinfo=datetime.timezone.utc),
    )


class FakeChannel:
    def __init__(self, messages, channel_id=42):
        self._messages = messages  # newest first, like Discord
        self.id = channel_id

    async def history(self, limit):
        for m in self._messages[:limit]:
            yield m
