"""Runtime-switchable chat and image models and image size (`/model`).

An override picked in Discord is stored in data/model_settings.json and wins
over MODEL_CHAT / IMAGE_MODEL from .env; "default" clears it. Only models in
the curated lists below can be picked — each was verified against the bot's
actual call shapes (tools + reasoning_effort="none" for chat; generate + edit
for images; every image model at every size, generate + edit, 2026-09-25),
so a switch can't break replies. Background jobs keep their own
*_MODEL settings and don't follow a switch.

Cost hints are for the picker; real spend is tracked by chatbotfunc/usage.py.
"""

import json
import logging
import os
import threading
import time

logger = logging.getLogger("bot.model_settings")

_PATH = os.path.join("data", "model_settings.json")
_lock = threading.Lock()

# (model id, short description shown in the picker)
CHAT_CHOICES = [
    ("gpt-6-sol",  "Balanced quality · $2 / $10 per 1M tokens"),
    ("gpt-6-luna", "Cheapest & fastest · ~20× cheaper than sol"),
    ("gpt-5.4",    "Previous generation · a bit pricier than sol"),
]
IMAGE_CHOICES = [
    ("gpt-image-1-mini",    "Cheapest · ~1¢ per image"),
    ("gpt-image-2.5-flare", "Newest · ~2¢ per image"),
    ("gpt-image-1",         "Original · ~4¢ per image"),
]
SIZE_CHOICES = [
    ("1024x1024", "Square"),
    ("1536x1024", "Landscape · ~1.5× cost on gpt-image-1/mini"),
    ("1024x1536", "Portrait · ~1.5× cost on gpt-image-1/mini"),
    ("auto",      "Model picks the shape from the prompt"),
]
# Per-request shapes (AI tool / `/generate aspect:`), overriding the default size.
ASPECTS = {"square": "1024x1024", "landscape": "1536x1024", "portrait": "1024x1536"}

_CHOICES = {"chat": CHAT_CHOICES, "image": IMAGE_CHOICES, "size": SIZE_CHOICES}
_ENV = {
    "chat": ("MODEL_CHAT", "gpt-6-sol"),
    "image": ("IMAGE_MODEL", "gpt-image-1"),
    "size": ("IMAGE_SIZE", "1024x1024"),
}


def _load() -> dict:
    try:
        with open(_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def env_default(kind: str) -> str:
    key, fallback = _ENV[kind]
    return os.getenv(key, "").strip() or fallback


def override(kind: str) -> dict | None:
    """The stored override for kind, or None. Ignored if the model has since
    been dropped from the curated list."""
    entry = _load().get(kind)
    valid = {m for m, _ in _CHOICES[kind]}
    return entry if entry and entry.get("model") in valid else None


def current(kind: str) -> str:
    entry = override(kind)
    return entry["model"] if entry else env_default(kind)


def get_chat_model() -> str:
    return current("chat")


def get_image_model() -> str:
    return current("image")


def get_image_size() -> str:
    return current("size")


def aspect_for(width: int, height: int) -> str:
    """The supported size closest in shape to width x height (transforms keep
    the source image's orientation instead of following the default size)."""
    ratio = width / height if height else 1
    if ratio >= 1.2:
        return ASPECTS["landscape"]
    if ratio <= 1 / 1.2:
        return ASPECTS["portrait"]
    return ASPECTS["square"]


def set_model(kind: str, model: str | None, set_by: str) -> None:
    """Store an override; model=None clears it back to the .env default.
    For kind "size" the value is a size string (stored under "model" too)."""
    if model is not None and model not in {m for m, _ in _CHOICES[kind]}:
        raise ValueError(f"{model} is not a selectable {kind} model")
    with _lock:
        data = _load()
        if model is None:
            data.pop(kind, None)
        else:
            data[kind] = {"model": model, "set_by": set_by, "ts": int(time.time())}
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        tmp = _PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, _PATH)
    logger.info("%s model %s by %s", kind, f"set to {model}" if model else "reset to default", set_by)
