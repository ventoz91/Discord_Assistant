import os
import discord
from discord.ext import commands, bridge
import logging
import asyncio
from io import BytesIO
from funfunc.sandwich import make_random_sandwich
from AIfunc.simulate import ConversationSimulator
from AIfunc.responses import generate_image
from chatbotfunc.utils import split_message

logger = logging.getLogger("bot.fun")

# ── Help text ─────────────────────────────────────────────────────────────────

_CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "💬  CHAT": [
        ("!change [n]  ·  /personality change",        "Switch to personality #n, or random"),
        ("!new <descriptor>  ·  /personality new",     "Add a new personality"),
        ("!list  ·  /personality list",                "List all personalities"),
        ("!pin [n]  ·  /personality pin",              "Pin a personality to this channel"),
        ("!unpin  ·  /personality unpin",              "Remove the channel personality pin"),
        ("!simulate [p1] [p2] <topic>  ·  /simulate", "Debate between two personalities"),
    ],
    "🧠  MEMORY": [
        ("!learn [text]  ·  /learn",   "Store text or a file in memory"),
        ("!memory  ·  /memory",        "Memory stats for this channel"),
        ("!summarize  ·  /summarize",  "TL;DR of recent conversation"),
        ("!cleardocs  ·  /cleardocs",  "Remove stored docs (keeps messages)"),
        ("!clearall",                  "Wipe all memory — requires Manage Messages"),
    ],
    "🖼️  IMAGES": [
        ("!generate <prompt>  ·  /generate",  "Generate an image with AI"),
        ("!transform <inst>  ·  /transform",  "Transform an attached image"),
        ("!transform last <inst>",            "Transform the last image in this channel"),
        ("!image <query>  ·  /image",         "Search and describe an image"),
        ("(natural language)",                "Just ask in chat — it works too"),
    ],
    "🎮  GAMES": [
        ("!game X|O  ·  /game",        "Tic-Tac-Toe"),
        ("!snake  ·  /snake",          "Snake"),
        ("!adventure  ·  /adventure",  "ASCII dungeon, 8-directional movement"),
    ],
    "🖥️  SERVERS": [
        ("!minecraft  ·  /minecraft",               "Minecraft server panel"),
        ("!start_valheim  ·  /valheim start",       "Start Valheim"),
        ("!stop_valheim  ·  /valheim stop",         "Stop Valheim"),
        ("!valheim_status  ·  /valheim status",     "Valheim status"),
        ("!start_enshrouded  ·  /enshrouded start", "Start Enshrouded"),
        ("!stop_enshrouded  ·  /enshrouded stop",   "Stop Enshrouded"),
    ],
    "🎲  MISC": [
        ("!sandwich  ·  /sandwich",  "Random sandwich with an AI image"),
    ],
}


def _build_help_text() -> str:
    lines = [
        "```",
        "╔══════════════════════════════════════════════╗",
        "║          B O T   C O M M A N D S            ║",
        "╚══════════════════════════════════════════════╝",
        "```",
        "",
    ]
    for label, entries in _CATEGORIES.items():
        lines.append(f"**{label}** {'─' * 30}")
        for cmd, desc in entries:
            lines.append(f"`{cmd}`  —  {desc}")
        lines.append("")
    return "\n".join(lines).rstrip()


class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Help / commands ───────────────────────────────────────────────────────

    async def _post_help(self, ctx):
        await ctx.defer()
        text = _build_help_text()
        chunks = split_message(text)
        await ctx.respond(chunks[0])
        for chunk in chunks[1:]:
            await ctx.channel.send(chunk)

    @bridge.bridge_command(name="commands", description="Show all bot commands")
    async def show_commands(self, ctx):
        await self._post_help(ctx)

    @bridge.bridge_command(name="help", description="Show all bot commands")
    async def show_help(self, ctx):
        await self._post_help(ctx)

    # ── Simulate (prefix keeps flexible *args; slash has explicit params) ──────

    @commands.command(name="simulate")
    async def simulate_prefix(self, ctx, *args):
        if len(args) < 1:
            await ctx.send("Please provide a topic for the debate.")
            return
        topic = args[-1]
        personalities = args[:-1]
        if len(personalities) > 2:
            await ctx.send("Usage: `!simulate [p1] [p2] <topic>`")
            return
        try:
            personality_indices = [int(i) for i in personalities]
        except ValueError:
            await ctx.send("Personality indices must be numbers. Use `!list` to see them.")
            return
        await self._simulate_impl(ctx, topic, personality_indices)

    @discord.slash_command(name="simulate", description="Simulate a debate between two personalities")
    async def simulate_slash(self, ctx,
        topic: discord.Option(str, "Topic for the debate"),
        p1: discord.Option(int, "First personality index (see /personality list)", required=False) = None,
        p2: discord.Option(int, "Second personality index", required=False) = None,
        turns: discord.Option(int, "Number of turns (2–12, default 6)", required=False) = 6):
        await ctx.defer()
        turns = max(2, min(turns, 12))
        personality_indices = [i for i in [p1, p2] if i is not None]
        await self._simulate_impl(ctx, topic, personality_indices, turns)

    async def _simulate_impl(self, ctx, topic: str, personality_indices: list, turns: int = 6):
        api_key = os.getenv("OPENAI_API_KEY")
        simulator = ConversationSimulator(api_key, os.getenv("MODEL_CHAT"))
        first = True
        async for label, text in simulator.simulate_conversation(topic, personality_indices, turns):
            if label == "intro":
                msg = text
            elif label == "judge":
                msg = f"**⚖️ Verdict**\n{text}"
            elif label == "error":
                msg = text
            else:
                msg = f"**{label}:** {text}"

            for chunk in split_message(msg, 2000):
                if first:
                    await ctx.respond(chunk)
                    first = False
                else:
                    await ctx.channel.send(chunk)

            if label not in ("intro", "error"):
                await asyncio.sleep(2)

    # ── Sandwich ──────────────────────────────────────────────────────────────

    @bridge.bridge_command(description="Generate a random sandwich with an image")
    async def sandwich(self, ctx):
        await ctx.defer()
        description = make_random_sandwich()
        image_prompt = f"Photorealistic food photography of {description}, gourmet presentation on a wooden board, soft professional lighting, shallow depth of field"
        image_bytes = await generate_image(image_prompt)
        if isinstance(image_bytes, bytes):
            await ctx.respond(
                description,
                file=discord.File(fp=BytesIO(image_bytes), filename="sandwich.png"),
            )
        else:
            await ctx.respond(description)


def setup(bot):
    bot.add_cog(FunCog(bot))
