import random
import os
import json

_CHANNEL_PIN_PATH = os.path.join("data", "channel_personalities.json")


class PersonalityManager:
    def __init__(self, filepath=".env"):
        self.filepath = filepath
        self.personalities = self.read_personalities_from_file()
        self._pins_cache: dict | None = None

    def read_personalities_from_file(self):
        if not os.path.exists(self.filepath):
            return []
        with open(self.filepath, "r") as f:
            lines = f.readlines()
        return [
            line.strip()[len("PERSONALITY="):]
            for line in lines
            if line.strip().startswith("PERSONALITY=")
        ]

    def add_personality(self, new_personality):
        if new_personality not in self.personalities:
            with open(self.filepath, "a") as f:
                f.write(f"PERSONALITY={new_personality}\n")
            self.personalities = self.read_personalities_from_file()
            return True
        return False

    def remove_personality(self, index):
        if not os.path.exists(self.filepath):
            return None
        with open(self.filepath, "r") as f:
            all_lines = f.readlines()

        personalities = [
            line.strip()[len("PERSONALITY="):]
            for line in all_lines
            if line.strip().startswith("PERSONALITY=")
        ]
        other_lines = [l for l in all_lines if not l.strip().startswith("PERSONALITY=")]

        adjusted_index = index - 1
        if not (0 <= adjusted_index < len(personalities)):
            return None

        removed = personalities.pop(adjusted_index)

        with open(self.filepath, "w") as f:
            for line in other_lines:
                f.write(line)
            for p in personalities:
                f.write(f"PERSONALITY={p}\n")

        self.personalities = self.read_personalities_from_file()
        return removed

    def get_active(self) -> str:
        """Return the last persisted active personality, falling back to index 0."""
        if not os.path.exists(self.filepath):
            return self.personalities[0] if self.personalities else ""
        with open(self.filepath, "r") as f:
            for line in f:
                if line.strip().startswith("ACTIVE_PERSONALITY="):
                    return line.strip()[len("ACTIVE_PERSONALITY="):]
        return self.personalities[0] if self.personalities else ""

    def set_active(self, descriptor: str):
        """Persist the active personality to .env as ACTIVE_PERSONALITY=."""
        if not os.path.exists(self.filepath):
            return
        with open(self.filepath, "r") as f:
            lines = f.readlines()
        existing = any(l.strip().startswith("ACTIVE_PERSONALITY=") for l in lines)
        if existing:
            lines = [
                f"ACTIVE_PERSONALITY={descriptor}\n" if l.strip().startswith("ACTIVE_PERSONALITY=") else l
                for l in lines
            ]
        else:
            lines.append(f"ACTIVE_PERSONALITY={descriptor}\n")
        with open(self.filepath, "w") as f:
            f.writelines(lines)

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

