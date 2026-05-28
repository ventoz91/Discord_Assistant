import random
import os
from chatbotfunc.utils import async_chat_completion


class PersonalityManager:
    def __init__(self, filepath=".env"):
        self.filepath = filepath
        self.personalities = self.read_personalities_from_file()

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

    def get_random_personality(self):
        return random.choice(self.personalities)

    def get_personality(self, index):
        if 0 <= index < len(self.personalities):
            return self.personalities[index]
        return None

    async def get_personality_name(self, model, personality, temperature=0.7):
        prompt = f"As a {personality}, if you had a first and last name, what would it be? Please type first and last name only"
        response = await async_chat_completion(
            model=model,
            messages=[{"role": "system", "content": prompt}],
            temperature=temperature,
            top_p=0.9,
            max_completion_tokens=10,
        )
        return response.choices[0].message.content.strip()
