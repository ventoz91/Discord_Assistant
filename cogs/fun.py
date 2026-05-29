import discord
from discord.ext import commands, bridge
import logging
import os
import asyncio
from io import BytesIO
from funfunc.prompt import GPTSearchPrompt
from funfunc.sandwich import make_random_sandwich
from AIfunc.simulate import ConversationSimulator
from AIfunc.responses import generate_image
from chatbotfunc.utils import split_message

logger = logging.getLogger("bot.fun")

# ── /commands help menu ───────────────────────────────────────────────────────

_CATEGORIES: dict[str, tuple[discord.Color, list[tuple[str, str]]]] = {
    "💬 Chat": (discord.Color.blurple(), [
        ("`!change [n]` / `/personality change`",   "Switch to personality #n, or random"),
        ("`!new <text>` / `/personality new`",       "Add a new personality descriptor"),
        ("`!list` / `/personality list`",            "List all personalities"),
        ("`!pin [n]` / `/personality pin`",          "Pin a personality to this channel"),
        ("`!unpin` / `/personality unpin`",          "Remove the channel personality pin"),
        ("`!simulate [p1] [p2] <topic>` / `/simulate`", "Simulate a debate between two personalities"),
    ]),
    "🧠 Memory": (discord.Color.purple(), [
        ("`!learn [text]` / `/learn`",   "Store text or an attached file in memory"),
        ("`!memory` / `/memory`",        "Show memory stats for this channel"),
        ("`!summarize` / `/summarize`",  "TL;DR of recent conversation"),
        ("`!cleardocs` / `/cleardocs`",  "Remove stored documents (keeps message history)"),
        ("`!clearall`",                  "Wipe all memory for this channel (Manage Messages required)"),
    ]),
    "🖼️ Images": (discord.Color.green(), [
        ("`!generate <prompt>` / `/generate`",            "Generate an image with AI"),
        ("`!transform <instructions>` / `/transform`",    "Transform an attached image"),
        ("`!transform last <instructions>`",              "Transform the most recent image in this channel"),
        ("`!image <query>` / `/image`",                   "Search and describe an image"),
        ("*(natural language)*",                          "Ask the bot to generate or transform in conversation"),
    ]),
    "🎮 Games": (discord.Color.orange(), [
        ("`!game X|O` / `/game`",     "Play Tic-Tac-Toe"),
        ("`!snake` / `/snake`",       "Play Snake"),
        ("`!adventure` / `/adventure`", "ASCII dungeon (QUD-style, 8-directional movement)"),
    ]),
    "🖥️ Servers": (discord.Color.dark_gray(), [
        ("`!minecraft` / `/minecraft`",                         "Open the Minecraft server panel"),
        ("`!start_valheim` / `/valheim start`",                 "Start the Valheim server"),
        ("`!stop_valheim` / `/valheim stop`",                   "Stop the Valheim server"),
        ("`!valheim_status` / `/valheim status`",               "Check Valheim server status"),
        ("`!start_enshrouded` / `/enshrouded start`",           "Start the Enshrouded server"),
        ("`!stop_enshrouded` / `/enshrouded stop`",             "Stop the Enshrouded server"),
    ]),
    "🎲 Misc": (discord.Color.teal(), [
        ("`!sandwich` / `/sandwich`", "Generate a random sandwich with an image"),
        ("`!prompt <topic>` / `/prompt`", "Generate a Google search URL for a topic"),
    ]),
}


def _home_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📖 Commands",
        description="Select a category to see available commands.",
        color=discord.Color.blurple(),
    )
    for label, (_, entries) in _CATEGORIES.items():
        embed.add_field(name=label, value=f"{len(entries)} commands", inline=True)
    return embed


def _category_embed(label: str) -> discord.Embed:
    color, entries = _CATEGORIES[label]
    embed = discord.Embed(title=f"{label} Commands", color=color)
    for name, desc in entries:
        embed.add_field(name=name, value=desc, inline=False)
    return embed


class _CommandsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self._show_home()

    def _show_home(self):
        self.clear_items()
        for i, label in enumerate(_CATEGORIES):
            self.add_item(_CategoryButton(label, row=i // 5))

    def _show_category(self, label: str):
        self.clear_items()
        self.add_item(_BackButton())


class _CategoryButton(discord.ui.Button):
    def __init__(self, label: str, row: int):
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=row)

    async def callback(self, interaction: discord.Interaction):
        view: _CommandsView = self.view
        view._show_category(self.label)
        await interaction.response.edit_message(embed=_category_embed(self.label), view=view)


class _BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="← Back", style=discord.ButtonStyle.secondary, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: _CommandsView = self.view
        view._show_home()
        await interaction.response.edit_message(embed=_home_embed(), view=view)


class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Commands help menu ────────────────────────────────────────────────────

    @bridge.bridge_command(name="commands", description="Browse all bot commands by category")
    async def show_commands(self, ctx):
        await ctx.defer()
        view = _CommandsView()
        await ctx.respond(embed=_home_embed(), view=view)

    # ── Prompt ────────────────────────────────────────────────────────────────

    @bridge.bridge_command(description="Generate a Google search URL for a topic via GPT")
    async def prompt(self, ctx, *, topic: str):
        await ctx.defer()
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            generator = GPTSearchPrompt(api_key, os.getenv("MODEL_CHAT", "gpt-3.5-turbo"))
            search_query = await generator.generate_search_query(topic)
            if search_query:
                await ctx.respond(GPTSearchPrompt.construct_google_search_url(search_query))
            else:
                await ctx.respond("Failed to generate search query.")
        except Exception as e:
            logger.exception("prompt command failed")
            await ctx.respond(f"Error: {e}")

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
