import random
import asyncio
from openai import AsyncOpenAI
from chatbotfunc.personalitymanager import PersonalityManager
from AIfunc.responses import BASE_SYSTEM_PROMPT

personality_manager = PersonalityManager()

DEBATE_ADDENDUM = (
    "\n\nYou are in a live debate. Be direct and punchy. Respond specifically "
    "to what was just said. Stay fully in character. Keep it under 3 sentences."
)

JUDGE_PROMPT = (
    "You are an impartial, entertaining debate judge. You've just watched a debate. "
    "Declare a winner, briefly explain why in their favour, and make it fun. 2-3 sentences max."
)


class ConversationSimulator:
    def __init__(self, openai_api_key, model_chat):
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model_chat = model_chat

    async def simulate_conversation(self, topic: str, personality_indices: list, turns: int = 6):
        """Async generator — yields (label, text) tuples as each piece is ready.

        Labels: 'intro', speaker name, 'judge', 'error'
        """
        personalities = personality_manager.read_personalities_from_file()
        if len(personalities) < 2:
            yield ("error", "Not enough personalities loaded to run a simulation.")
            return

        if len(personality_indices) == 2:
            try:
                p1, p2 = [personalities[i - 1] for i in personality_indices]
            except IndexError:
                yield ("error", "Invalid personality index — use `!list` to see available numbers.")
                return
        else:
            p1, p2 = random.sample(personalities, 2)

        # Fetch both names in parallel
        name1, name2 = await asyncio.gather(
            personality_manager.get_personality_name(self.model_chat, p1),
            personality_manager.get_personality_name(self.model_chat, p2),
        )

        yield ("intro", f"🎭 **{name1}** vs **{name2}**\nTopic: *{topic}*")

        speakers = [(name1, p1), (name2, p2)]
        log: list[tuple[str, str]] = []  # (speaker_name, text)

        for i in range(turns):
            current_name, current_personality = speakers[i % 2]

            system_content = BASE_SYSTEM_PROMPT.format(personality=current_personality) + DEBATE_ADDENDUM

            # Build full conversation history from each speaker's perspective
            messages = [{"role": "system", "content": system_content}]
            for speaker, text in log:
                role = "assistant" if speaker == current_name else "user"
                messages.append({"role": role, "content": f"{speaker}: {text}"})

            if i == 0:
                messages.append({"role": "user", "content": f"Open the debate on: {topic}"})

            response = await self.client.chat.completions.create(
                model=self.model_chat,
                messages=messages,
                temperature=1.5,
                top_p=0.9,
                max_completion_tokens=120,
            )
            reply = response.choices[0].message.content.strip()
            log.append((current_name, reply))
            yield (current_name, reply)

        # Judge
        transcript = "\n".join(f"{name}: {text}" for name, text in log)
        judge_messages = [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"Topic: {topic}\n\n{transcript}"},
        ]
        judge_response = await self.client.chat.completions.create(
            model=self.model_chat,
            messages=judge_messages,
            temperature=1.0,
            max_completion_tokens=150,
        )
        yield ("judge", judge_response.choices[0].message.content.strip())
