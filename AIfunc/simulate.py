import random
import asyncio
from openai import AsyncOpenAI
from chatbotfunc.utils import fetch_message_history
from chatbotfunc.personalitymanager import PersonalityManager

personality_manager = PersonalityManager()

class ConversationSimulator:
    def __init__(self, openai_api_key, model_chat):
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model_chat = model_chat

    async def simulate_conversation(self, channel, topic, personality_indices, turns, bot):
        discord_history = await fetch_message_history(channel, bot)

        # Read personalities from file
        personalities = personality_manager.read_personalities_from_file()
        if len(personalities) < 2:
            return ["Not enough personalities to simulate a conversation."]

        # Select personalities based on provided indices or choose randomly
        if personality_indices and len(personality_indices) == 2:
            try:
                personality_one, personality_two = [personalities[i-1] for i in personality_indices]
            except IndexError:
                return ["Invalid personality indices. Please choose valid numbers based on the available personalities."]
        else:
            personality_one, personality_two = random.sample(personalities, 2)

        personality_one_name = await personality_manager.get_personality_name(self.model_chat, personality_one)
        personality_two_name = await personality_manager.get_personality_name(self.model_chat, personality_two)

        # Initialize conversation context
        conversation_context = [{"role": "system", "content": f"Let's discuss: {topic}."}]

        # Generate conversation replies
        for i in range(turns):
            current_role = "assistant" if i % 2 == 0 else "user"
            current_personality = personality_one if current_role == "assistant" else personality_two
            current_personality_name = personality_one_name if current_role == "assistant" else personality_two_name
            length_limit_directive = "Please limit your response to 500 characters."
            response_request = "" if i == turns - 1 else " What is your response to this?"
            if i == 0:
                prompt_text = f"As a {current_personality}, {current_personality}: What is your opinion on {topic}?{response_request} {length_limit_directive}"
            else:
                last_message = conversation_context[-1]["content"]
                prompt_text = f"As a {current_personality}, {last_message}{response_request} {length_limit_directive}"
            prompt = [{"role": current_role, "content": prompt_text}]

            response = await self.client.chat.completions.create(
                model=self.model_chat,
                messages=prompt,
                temperature=1.5,
                top_p=0.9,
                max_completion_tokens=150
            )
            gpt_reply = response.choices[0].message.content.strip()
            conversation_context.append({"role": "user", "content": f"{gpt_reply}"})

        # Format the conversation history for output
        conversation_lines = []
        for idx, message in enumerate(conversation_context):
            if idx > 0:
                conversation_lines.append("----------------------------------------")
            label = personality_one_name if (idx - 1) % 2 == 0 else personality_two_name
            conversation_lines.append(f"**{label}:** {message['content']}")

        return conversation_lines