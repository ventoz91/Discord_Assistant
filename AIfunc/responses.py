from chatbotfunc.utils import async_chat_completion
from openai import OpenAI
import openai
import logging
import os
import io
import json
import asyncio
import base64
from PIL import Image

logger = logging.getLogger("bot.responses")

openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY not set.")
client = OpenAI(api_key=openai_api_key)

BASE_SYSTEM_PROMPT = """You are an AI assistant living in a Discord server. Your responses are shaped entirely by the personality below — treat it as your identity, not a costume.

PLATFORM: Discord chat. Be conversational and concise by default. Match the energy of the conversation — casual gets casual back, serious gets serious back. Never open with hollow filler like "Great question!" or "Certainly!". Format code in triple-backtick blocks. If a response genuinely needs to exceed 2000 characters, break at a logical point and say you're continuing.

CHARACTER: Fully embody the personality below at all times. It defines your voice, humour, quirks, and worldview. Do not break character or acknowledge being an AI unless directly and sincerely asked. The personality shapes how you say things — not whether facts are accurate.

CONTEXT: Focus on the most recent message. Use conversation history as supporting context only — don't rehash old topics unless directly relevant. When RELEVANT CONTEXT FROM MEMORY is provided, treat it as background knowledge you naturally possess; do not announce that you're referencing it.

SPEAKERS: This is a group chat. Human messages are prefixed with the speaker's display name ("Name: message") — keep track of who said what and address the right person. Never prefix your own replies with a name.

VISUAL CONTENT: You CAN see images, gifs, and videos — they are analyzed when posted, and your reply right after one reflects what you genuinely saw. In history, past visuals appear only as placeholders like [shared image: cat.png] because the pixels aren't re-attached to every request — that does NOT mean you never saw them. If you reacted to it, you saw it; stand by your reaction. Never claim you can't see images, never speculate about placeholders, attachments, or how your vision works — stay in the conversation. The only rule: don't invent contents for a visual you never reacted to.

UNCERTAINTY: If you don't know something, say so in character rather than fabricating. A confident wrong answer is worse than an honest "I'm not sure."

Personality: {personality}"""


async def generate_gpt_response(message_history, chatgpt_behaviour, max_completion_tokens=None, temperature=None, top_p=0.9, rag_context=None, tools=None, auto_resolve=None, user_context=None, debate_context=None):
    # auto_resolve: dict[tool_name, async callable(args_dict) -> str]
    # Tools listed here are executed internally; only remaining tool calls are returned to the caller.
    max_tokens = max_completion_tokens or int(os.getenv("MAX_TOKENS", "500"))
    temperature = temperature if temperature is not None else float(os.getenv("TEMPERATURE", "1.5"))

    system_content = BASE_SYSTEM_PROMPT.format(personality=chatgpt_behaviour)
    if user_context:
        system_content += f"\n\nUSER PROFILE:\n{user_context}"
    if debate_context:
        system_content += (
            "\n\nONGOING THREADS YOU REMEMBER (bring one up naturally if it genuinely fits — "
            f"never force it):\n{debate_context}"
        )
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

        # Agentic loop: execute auto-resolvable tools (search, suggest) and feed
        # results back so the model can chain calls — search, refine, search
        # again — up to MAX_AGENT_TURNS follow-up rounds. Non-auto tool calls
        # (image gen, restart) accumulate and are returned to the caller. On
        # the final allowed round the auto tools are withheld so the model
        # must produce an answer instead of another tool call.
        max_turns = int(os.getenv("MAX_AGENT_TURNS", "4"))
        dispatch = []
        turn = 0
        convo = list(messages)
        while auto_resolve and tool_calls and turn < max_turns:
            resolvable = [tc for tc in tool_calls if tc.function.name in auto_resolve]
            dispatch += [tc for tc in tool_calls if tc.function.name not in auto_resolve]
            if not resolvable:
                tool_calls = []
                break
            turn += 1
            # Include only the resolvable tool calls in the assistant message
            # so every tool_call_id has a matching tool result.
            convo.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in resolvable
                ]
            })
            for tc in resolvable:
                try:
                    result = await auto_resolve[tc.function.name](json.loads(tc.function.arguments))
                except Exception as exc:
                    logger.exception("auto-resolve tool %s failed", tc.function.name)
                    result = f"Tool error: {exc}"
                convo.append({"role": "tool", "tool_call_id": tc.id, "content": result})

            last_round = turn >= max_turns
            follow_tools = (
                [t for t in (tools or []) if t["function"]["name"] not in auto_resolve]
                if last_round else tools
            )
            follow_kwargs = dict(
                model=os.getenv("MODEL_CHAT"),
                messages=convo,
                temperature=temperature,
                top_p=top_p,
                max_completion_tokens=max_tokens,
            )
            if follow_tools:
                follow_kwargs["tools"] = follow_tools

            follow_response = await async_chat_completion(**follow_kwargs)
            if not follow_response.choices:
                tool_calls = []
                break
            choice = follow_response.choices[0].message
            content = choice.content or ""
            tool_calls = choice.tool_calls or []

        # Whatever survived the loop that isn't auto-resolvable goes to the caller
        remaining = [tc for tc in (tool_calls or [])
                     if not auto_resolve or tc.function.name not in auto_resolve]
        return (content, dispatch + remaining) if tools else content
    except Exception as e:
        logger.exception("generate_gpt_response failed")
        err = f"An error occurred while generating a response. Details: {e}"
        return (err, []) if tools else err
    

async def analyze_image(base64_image: str, instructions: str, message_history: list, chatgpt_behaviour: str, user_context: str = None) -> str:
    system_content = BASE_SYSTEM_PROMPT.format(personality=chatgpt_behaviour)
    if user_context:
        system_content += f"\n\nUSER PROFILE:\n{user_context}"
    messages = [{"role": "system", "content": system_content}] + message_history
    # base64_image: single base64 string, or a list of them (e.g. sampled video frames)
    images = base64_image if isinstance(base64_image, list) else [base64_image]
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": instructions}] + [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}}
            for img in images
        ],
    })
    try:
        response = await async_chat_completion(
            model=os.getenv("MODEL_CHAT", "gpt-4o"),
            messages=messages,
            max_completion_tokens=int(os.getenv("ANALYZE_MAX_TOKENS", "500")),
        )
        if response.choices:
            if response.usage:
                logger.debug("analyze_image tokens: %d", response.usage.total_tokens)
            return response.choices[0].message.content or ""
        return ""
    except Exception:
        logger.exception("analyze_image failed")
        return ""

async def generate_image(prompt, model="gpt-image-1", size=None, quality=None, n=1):
    size = size or os.getenv("IMAGE_SIZE", "1024x1024")
    quality = quality or os.getenv("IMAGE_QUALITY", "medium")
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
        return image_bytes

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


async def transform_image(image_bytes: bytes, instructions: str, size=None, quality=None):
    size = size or os.getenv("IMAGE_SIZE", "1024x1024")
    quality = quality or os.getenv("IMAGE_QUALITY", "medium")
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
