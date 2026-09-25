"""OpenAI usage and cost tracking (`/usage`).

Every chat completion goes through chatbotfunc.utils.async_chat_completion,
which calls record_chat(); generate_image/transform_image call record_image().
Totals are aggregated per day -> feature -> model in data/usage.json (last
USAGE_RETENTION_DAYS, default 90) — token counts are exact (from the API's
usage block), dollar figures are estimates from PRICES below.

PRICES are USD per 1M tokens, list price as of 2026-09-25
(developers.openai.com/api/docs/pricing). Models missing from the table are
still counted, just without a cost. Update the table when prices change.
"""

import datetime
import json
import logging
import os
import threading

logger = logging.getLogger("bot.usage")

_PATH = os.path.join("data", "usage.json")
_lock = threading.Lock()

# chat: (input, cached input, output)
CHAT_PRICES = {
    "gpt-6-sol":    (2.00, 0.20, 10.00),
    "gpt-6-luna":   (0.10, 0.01, 0.50),
    "gpt-5.4":      (2.50, 0.25, 15.00),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
}
# image: (text input, image input, image output)
IMAGE_PRICES = {
    "gpt-image-1":         (5.00, 10.00, 40.00),
    "gpt-image-1-mini":    (2.00, 2.50, 8.00),
    "gpt-image-2":         (5.00, 8.00, 30.00),
    "gpt-image-2.5-flare": (5.00, 8.00, 30.00),
}

_warned_unpriced: set[str] = set()


def _today() -> str:
    return datetime.date.today().isoformat()


def _load() -> dict:
    try:
        with open(_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _add(feature: str, model: str, *, input_tokens: int, cached_tokens: int = 0,
         output_tokens: int = 0, images: int = 0, cost: float | None):
    with _lock:
        data = _load()
        day = data.setdefault(_today(), {})
        row = day.setdefault(feature, {}).setdefault(model, {
            "calls": 0, "input": 0, "cached": 0, "output": 0, "images": 0, "cost": 0.0, "unpriced": 0,
        })
        row["calls"] += 1
        row["input"] += input_tokens
        row["cached"] += cached_tokens
        row["output"] += output_tokens
        row["images"] += images
        if cost is None:
            row["unpriced"] += 1
        else:
            row["cost"] = round(row["cost"] + cost, 6)

        keep = int(os.getenv("USAGE_RETENTION_DAYS", "90"))
        cutoff = (datetime.date.today() - datetime.timedelta(days=keep)).isoformat()
        for d in [d for d in data if d < cutoff]:
            del data[d]

        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        tmp = _PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, _PATH)


def _price(table: dict, model: str):
    # Dated snapshots (gpt-5.4-2026-03-05) price like their base model.
    for name in sorted(table, key=len, reverse=True):
        if model == name or model.startswith(name + "-2"):
            return table[name]
    if model not in _warned_unpriced:
        _warned_unpriced.add(model)
        logger.warning("no price for model %s — usage counted without cost", model)
    return None


def record_chat(model: str, usage, feature: str):
    """usage: the `usage` block of a chat completion (may be None)."""
    if usage is None:
        return
    try:
        prompt = usage.prompt_tokens or 0
        details = getattr(usage, "prompt_tokens_details", None)
        cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        output = usage.completion_tokens or 0
        price = _price(CHAT_PRICES, model)
        cost = None
        if price:
            p_in, p_cached, p_out = price
            cost = ((prompt - cached) * p_in + cached * p_cached + output * p_out) / 1_000_000
        _add(feature, model, input_tokens=prompt, cached_tokens=cached, output_tokens=output, cost=cost)
    except Exception:
        logger.exception("usage recording failed (chat)")


def record_image(model: str, usage, feature: str):
    """usage: the `usage` block of an images.generate/edit response."""
    try:
        text_in = image_in = output = 0
        if usage is not None:
            details = getattr(usage, "input_tokens_details", None)
            text_in = (getattr(details, "text_tokens", 0) or 0) if details else (usage.input_tokens or 0)
            image_in = (getattr(details, "image_tokens", 0) or 0) if details else 0
            output = usage.output_tokens or 0
        price = _price(IMAGE_PRICES, model) if usage is not None else None
        cost = None
        if price:
            p_text, p_img, p_out = price
            cost = (text_in * p_text + image_in * p_img + output * p_out) / 1_000_000
        _add(feature, model, input_tokens=text_in + image_in, output_tokens=output, images=1, cost=cost)
    except Exception:
        logger.exception("usage recording failed (image)")


def summarize(days: int) -> dict:
    """Totals over the last `days` days (today inclusive):
    {"cost", "calls", "images", "unpriced", "by_feature": {f: cost}, "by_model": {m: cost}}."""
    since = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
    out = {"cost": 0.0, "calls": 0, "images": 0, "unpriced": 0, "by_feature": {}, "by_model": {}}
    for day, features in _load().items():
        if day < since:
            continue
        for feature, models in features.items():
            for model, row in models.items():
                out["cost"] += row["cost"]
                out["calls"] += row["calls"]
                out["images"] += row["images"]
                out["unpriced"] += row["unpriced"]
                out["by_feature"][feature] = out["by_feature"].get(feature, 0.0) + row["cost"]
                out["by_model"][model] = out["by_model"].get(model, 0.0) + row["cost"]
    return out
