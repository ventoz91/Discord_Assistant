from chatbotfunc.utils import async_chat_completion
import os
from dotenv import load_dotenv

load_dotenv()

async def generate_gpt_response(message_history, chatgpt_behaviour, max_tokens=None, temperature=1.5, top_p=0.9):
    # Load the max tokens from environment if not provided
    max_tokens = max_tokens or int(os.getenv("MAX_TOKENS"))

    # Prepare the messages, including the system behavior message
    messages = [{"role": "system", "content": chatgpt_behaviour}] + message_history
    messages.append({"role": "assistant", "content": "What is your reply?"})

    try:
        response = await async_chat_completion(
            model=os.getenv("MODEL_CHAT"),
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens
        )

        if response.choices:
            return response.choices[0].message.content
        else:
            return "Sorry, I couldn't generate a response."
    except Exception as e:
        error_msg = f"Error generating response: {e}"
        print(error_msg)
        return f"An error occurred while generating a response. Details: {error_msg}"
