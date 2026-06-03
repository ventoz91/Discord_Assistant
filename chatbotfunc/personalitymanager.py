import os
import json

_CHANNEL_PIN_PATH = os.path.join("data", "channel_personalities.json")
_PERSONALITY_PATH = os.path.join("data", "personalities.json")


def _read_env_personalities(env_path: str) -> tuple[list[str], str]:
    """Read personality list and active descriptor from a .env file."""
    personalities = []
    active = ""
    if not os.path.exists(env_path):
        return personalities, active
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("PERSONALITY="):
                personalities.append(line[len("PERSONALITY="):])
            elif line.startswith("ACTIVE_PERSONALITY="):
                active = line[len("ACTIVE_PERSONALITY="):]
    return personalities, active


class PersonalityManager:
    """Manages personality descriptors stored in data/personalities.json.

    On first run, auto-migrates PERSONALITY= and ACTIVE_PERSONALITY= entries
    from the .env file so existing personalities are preserved. After migration
    the .env entries are left in place but ignored.
    """

    def __init__(self, env_path: str = ".env"):
        self.env_path = env_path
        os.makedirs("data", exist_ok=True)
        self._ensure_store()
        self._data = self._load()
        self._pins_cache: dict | None = None

    # ── Internal store ────────────────────────────────────────────────────────

    def _ensure_store(self):
        """Create personalities.json from .env if it doesn't exist yet."""
        if os.path.exists(_PERSONALITY_PATH):
            return
        personalities, active = _read_env_personalities(self.env_path)
        data = {
            "personalities": personalities,
            "active": active or (personalities[0] if personalities else ""),
        }
        with open(_PERSONALITY_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> dict:
        with open(_PERSONALITY_PATH, "r") as f:
            return json.load(f)

    def _save(self):
        with open(_PERSONALITY_PATH, "w") as f:
            json.dump(self._data, f, indent=2)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def personalities(self) -> list[str]:
        return self._data["personalities"]

    def add_personality(self, descriptor: str) -> bool:
        if descriptor in self._data["personalities"]:
            return False
        self._data["personalities"].append(descriptor)
        self._save()
        return True

    def remove_personality(self, index: int) -> str | None:
        adjusted = index - 1
        if not (0 <= adjusted < len(self._data["personalities"])):
            return None
        removed = self._data["personalities"].pop(adjusted)
        if self._data["active"] == removed:
            self._data["active"] = self._data["personalities"][0] if self._data["personalities"] else ""
        self._save()
        return removed

    def get_active(self) -> str:
        return self._data.get("active", self._data["personalities"][0] if self._data["personalities"] else "")

    def set_active(self, descriptor: str):
        self._data["active"] = descriptor
        self._save()

    # ── Per-channel personality pins ──────────────────────────────────────────

    def _load_pins(self) -> dict:
        if self._pins_cache is not None:
            return self._pins_cache
        if not os.path.exists(_CHANNEL_PIN_PATH):
            self._pins_cache = {}
        else:
            with open(_CHANNEL_PIN_PATH, "r") as f:
                self._pins_cache = json.load(f)
        return self._pins_cache

    def _save_pins(self, pins: dict):
        os.makedirs(os.path.dirname(_CHANNEL_PIN_PATH), exist_ok=True)
        with open(_CHANNEL_PIN_PATH, "w") as f:
            json.dump(pins, f, indent=2)
        self._pins_cache = pins

    def get_channel_personality(self, channel_id: int) -> str | None:
        return self._load_pins().get(str(channel_id))

    def set_channel_personality(self, channel_id: int, descriptor: str):
        pins = self._load_pins()
        pins[str(channel_id)] = descriptor
        self._save_pins(pins)

    def clear_channel_personality(self, channel_id: int) -> bool:
        pins = self._load_pins()
        if str(channel_id) in pins:
            del pins[str(channel_id)]
            self._save_pins(pins)
            return True
        return False
