from chatbotfunc.utils import async_chat_completion
from openai import OpenAI
import openai
import logging
import os
import io
import json
import aiohttp
import asyncio
import base64
from dotenv import load_dotenv
from PIL import Image
load_dotenv()

logger = logging.getLogger("bot.responses")

# Initialize the OpenAI client with your API key
openai_api_key = os.environ["OPENAI_API_KEY"]
if openai_api_key is None:
    raise ValueError("No OpenAI API key found. Make sure to set the OPENAI_API_KEY environment variable.")
client = OpenAI(api_key=openai_api_key)
openai.api_key = openai_api_key

BASE_SYSTEM_PROMPT = """You are an AI assistant living in a Discord server. Your responses are shaped entirely by the personality below — treat it as your identity, not a costume.

PLATFORM: Discord chat. Be conversational and concise by default. Match the energy of the conversation — casual gets casual back, serious gets serious back. Never open with hollow filler like "Great question!" or "Certainly!". Format code in triple-backtick blocks. If a response genuinely needs to exceed 2000 characters, break at a logical point and say you're continuing.

CHARACTER: Fully embody the personality below at all times. It defines your voice, humour, quirks, and worldview. Do not break character or acknowledge being an AI unless directly and sincerely asked. The personality shapes how you say things — not whether facts are accurate.

CONTEXT: Focus on the most recent message. Use conversation history as supporting context only — don't rehash old topics unless directly relevant. When RELEVANT CONTEXT FROM MEMORY is provided, treat it as background knowledge you naturally possess; do not announce that you're referencing it.

UNCERTAINTY: If you don't know something, say so in character rather than fabricating. A confident wrong answer is worse than an honest "I'm not sure."

Personality: {personality}"""


#Genereate gpt response with chat history and current behaviour
async def generate_gpt_response(message_history, chatgpt_behaviour, max_completion_tokens=None, temperature=1.5, top_p=0.9, rag_context=None, tools=None, auto_resolve=None):
    # auto_resolve: dict[tool_name, async callable(args_dict) -> str]
    # Tools listed here are executed internally; only remaining tool calls are returned to the caller.
    max_tokens = max_completion_tokens or int(os.getenv("MAX_TOKENS"))

    system_content = BASE_SYSTEM_PROMPT.format(personality=chatgpt_behaviour)
    if rag_context:
        system_content += "\n\nRELEVANT CONTEXT FROM MEMORY:\n" + "\n---\n".join(rag_context)
    messages = [{"role": "system", "content": system_content}] + message_history

    kwargs = dict(
        model=os.getenv("MODEL_CHAT"),
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_completion_tokens=max_tokens,
    )
    if tools:
        kwargs["tools"] = tools

    try:
        response = await async_chat_completion(**kwargs)

        if not response.choices:
            return ("Sorry, I couldn't generate a response.", []) if tools else "Sorry, I couldn't generate a response."

        choice = response.choices[0].message
        content = choice.content or ""
        tool_calls = choice.tool_calls or []

        # Auto-resolve tools (e.g. web search): execute them and make a second API call
        # so the model can incorporate the results into its final response.
        if auto_resolve and tool_calls:
            resolvable = [tc for tc in tool_calls if tc.function.name in auto_resolve]
            dispatch = [tc for tc in tool_calls if tc.function.name not in auto_resolve]

            if resolvable:
                # Build follow-up: include only the resolvable tool calls in the assistant
                # message so every tool_call_id has a matching tool result.
                assistant_msg = {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in resolvable
                    ]
                }
                follow_up = list(messages) + [assistant_msg]
                for tc in resolvable:
                    result = await auto_resolve[tc.function.name](json.loads(tc.function.arguments))
                    follow_up.append({"role": "tool", "tool_call_id": tc.id, "content": result})

                # Exclude auto-resolved tools from the follow-up to prevent re-triggering
                follow_up_tools = [t for t in (tools or []) if t["function"]["name"] not in auto_resolve]
                follow_up_kwargs = dict(
                    model=os.getenv("MODEL_CHAT"),
                    messages=follow_up,
                    temperature=temperature,
                    top_p=top_p,
                    max_completion_tokens=max_tokens,
                )
                if follow_up_tools:
                    follow_up_kwargs["tools"] = follow_up_tools

                follow_up_response = await async_chat_completion(**follow_up_kwargs)
                if follow_up_response.choices:
                    follow_up_choice = follow_up_response.choices[0].message
                    content = follow_up_choice.content or ""
                    dispatch = dispatch + (follow_up_choice.tool_calls or [])
                tool_calls = dispatch

        return (content, tool_calls) if tools else content
    except Exception as e:
        logger.exception("generate_gpt_response failed")
        err = f"An error occurred while generating a response. Details: {e}"
        return (err, []) if tools else err
    

#Anylyzes images with history and personality context
async def analyze_image(base64_image, instructions, message_history, chatgpt_behaviour):
    system_content = BASE_SYSTEM_PROMPT.format(personality=chatgpt_behaviour)
    messages = [{"role": "system", "content": system_content}] + message_history
    messages.append({"role": "user", "content": [{"type": "text", "text": instructions}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]})

    payload = {
        "model": os.getenv("MODEL_CHAT", "gpt-4o"),
        "messages": messages,
        "max_completion_tokens": 300
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {openai_api_key}"}

    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload) as response:
            response_json = await response.json()
            if 'usage' in response_json:
                logger.debug("analyze_image tokens: %d", response_json['usage']['total_tokens'])
            return response_json

async def generate_image(prompt, model="gpt-image-1", size="1024x1024", quality="medium", n=1):
    try:
        response = await asyncio.to_thread(
            client.images.generate,
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=n,
        )

        # gpt-image-1/2 always returns b64_json, never a URL
        image_b64 = response.data[0].b64_json
        if not image_b64:
            return None

        image_bytes = base64.b64decode(image_b64)
        return image_bytes  # return raw bytes; save to file or convert to data URL as needed

    except openai.BadRequestError as e:
        try:
            detail = e.response.json()
            msg = detail.get('error', {}).get('message', str(e))
        except Exception:
            msg = str(e)
        logger.warning("image request rejected by OpenAI: %s", msg)
        return msg

    except Exception as e:
        logger.exception("generate_image failed")
        return None


async def transform_image(image_bytes: bytes, instructions: str, size="1024x1024", quality="medium"):
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        png_buffer = io.BytesIO()
        img.save(png_buffer, format="PNG")
        png_buffer.seek(0)

        response = await asyncio.to_thread(
            client.images.edit,
            model="gpt-image-1",
            image=("image.png", png_buffer, "image/png"),
            prompt=instructions,
            size=size,
            quality=quality,
            n=1,
        )

        image_b64 = response.data[0].b64_json
        if not image_b64:
            return None
        return base64.b64decode(image_b64)

    except openai.BadRequestError as e:
        try:
            detail = e.response.json()
            msg = detail.get('error', {}).get('message', str(e))
        except Exception:
            msg = str(e)
        logger.warning("transform request rejected by OpenAI: %s", msg)
        return msg

    except Exception as e:
        logger.exception("transform_image failed")
        return None
