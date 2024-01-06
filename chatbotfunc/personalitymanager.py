import random
import os
from chatbotfunc.utils import async_chat_completion

class PersonalityManager:
    def __init__(self, filepath="personalities.env"):
        self.filepath = filepath
        self.personalities = self.read_personalities_from_file()

    # read personality file and return data
    def read_personalities_from_file(self):
        if not os.path.exists("personalities.env"):
            return []
        with open("personalities.env", "r") as file:
            lines = file.readlines()
            return [line.strip().split('=')[1] for line in lines if line.strip() and '=' in line]

    def add_personality(self, new_personality):
        if new_personality not in self.personalities:
            self.personalities.append(new_personality)
            with open(self.filepath, "a") as file:
                file.write(f"PERSONALITY{len(self.personalities)}={new_personality}\n")
            return True
        return False

    def get_random_personality(self):
        return random.choice(self.personalities)

    def get_personality(self, index):
        if 0 <= index < len(self.personalities):
            return self.personalities[index]
        return None
    
    async def get_personality_name(self, model, personality, temperature=0.7):
        # Construct a prompt to ask the personality for its name
        prompt = f"As a {personality}, if you had a first and last name, what would it be? Please type first and last name only"
        # Request a response from OpenAI
        response = await async_chat_completion(
            model=model,
            messages=[{"role": "system", "content": prompt}],
            temperature=temperature,
            top_p=0.9,
            max_tokens=10
        )
        # Extracting and returning the GPT response (name)
        return response.choices[0].message.content.strip()
