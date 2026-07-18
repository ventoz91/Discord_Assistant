"""Tool schemas and executors for the chat AI. Imported by cogs/chat.py.

GENERATE/TRANSFORM/RESTART are returned to the caller for handling;
SEARCH and SUGGEST are auto-resolved inside generate_gpt_response.
"""

import os
import random

from funfunc.web_search import web_search
from ragfunc.memory import async_retrieve

GENERATE_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": "Generate and post an image to the chat. Use this when the user explicitly asks for a picture, image, drawing, or photo of something.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Detailed image generation prompt describing what to create"}
            },
            "required": ["prompt"]
        }
    }
}

TRANSFORM_TOOL = {
    "type": "function",
    "function": {
        "name": "transform_image",
        "description": "Transform or modify the most recent image in this channel. Use this when the user asks to change, edit, modify, or transform the current or last image.",
        "parameters": {
            "type": "object",
            "properties": {
                "instructions": {"type": "string", "description": "Instructions describing how to transform the image"}
            },
            "required": ["instructions"]
        }
    }
}

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "google_search",
        "description": "Search the web for current information. Use this for recent events, specific facts, or anything that may be outside your training data.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"]
        }
    }
}

SUGGEST_TOOL = {
    "type": "function",
    "function": {
        "name": "suggest_activity",
        "description": (
            "Suggest something to do — either a bot feature or an activity previously "
            "mentioned by users in this channel. Call this when someone asks what to do, "
            "says they're bored, asks for a suggestion, or asks what the bot can do."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
}

RESTART_TOOL = {
    "type": "function",
    "function": {
        "name": "restart_bot",
        "description": (
            "Restart the bot process. Only call this when a user explicitly and "
            "politely asks you to restart, reboot, or reload yourself "
            "(e.g. 'could you restart please?'). Never call this for any other reason."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
}

BOT_SUGGESTIONS = [
    ("play Snake",                  "use !snake or /snake — button D-pad, score tracked"),
    ("play Tic-Tac-Toe",            "use !game X or !game O or /game"),
    ("explore the ASCII dungeon",   "use !adventure or /adventure — 8-directional roguelike"),
    ("generate an AI image",        "use !generate <prompt> or /generate"),
    ("transform an existing image", "post an image then use !transform or /transform"),
    ("make a random sandwich",      "use !sandwich or /sandwich — comes with an AI photo"),
    ("simulate a debate",           "use !simulate <topic> or /simulate — pick two personalities to argue"),
    ("search the web",              "just ask me to look something up — I have a search tool"),
    ("change my personality",       "use !change or /personality change"),
]


async def execute_search(args: dict) -> str:
    return await web_search(args.get("query", ""))


def make_suggest_executor(channel_id: int):
    async def _execute(args: dict) -> str:
        past = await async_retrieve(
            channel_id, "something fun activity let's do play", k=15, doc_type="message"
        )
        if past and random.random() < 0.5:
            snippet = random.choice(past)
            return f"A past activity mentioned in this channel: {snippet}\nUse this as inspiration for a suggestion."
        label, how = random.choice(BOT_SUGGESTIONS)
        return f"Suggest the user tries: {label} — {how}"

    return _execute


def is_bot_owner(user_id: int) -> bool:
    owner_ids = os.getenv("BOT_OWNER_IDS", "")
    allowed = {int(uid) for uid in owner_ids.split(',') if uid.strip()}
    return user_id in allowed
