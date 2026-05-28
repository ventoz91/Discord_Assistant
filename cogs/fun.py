import discord
from discord.ext import commands, bridge
import os
import asyncio
import subprocess
from funfunc.prompt import GPTSearchPrompt
from AIfunc.simulate import ConversationSimulator
from chatbotfunc.utils import split_message


class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
            await ctx.respond(f"Error: {e}")
            print(f"Error: {e}")

    # ── Simulate (prefix keeps flexible *args; slash has explicit params) ──────

    @commands.command(name="simulate")
    async def simulate_prefix(self, ctx, *args):
        if len(args) < 1:
            await ctx.send("Please provide a topic for the conversation.")
            return
        topic = args[-1]
        personalities = args[:-1]
        if len(personalities) > 2:
            await ctx.send("Please provide up to two personality indices followed by a topic.")
            return
        try:
            personality_indices = [int(i) for i in personalities]
        except ValueError:
            await ctx.send("Please provide valid personality indices (as numbers).")
            return
        await self._simulate_impl(ctx, topic, personality_indices)

    @discord.slash_command(name="simulate", description="Simulate a conversation between two personalities on a topic")
    async def simulate_slash(self, ctx,
        topic: discord.Option(str, "Topic for the conversation"),
        p1: discord.Option(int, "First personality index", required=False) = None,
        p2: discord.Option(int, "Second personality index", required=False) = None):
        await ctx.defer()
        personality_indices = [i for i in [p1, p2] if i is not None]
        await self._simulate_impl(ctx, topic, personality_indices)

    async def _simulate_impl(self, ctx, topic: str, personality_indices: list):
        api_key = os.getenv("OPENAI_API_KEY")
        simulator = ConversationSimulator(api_key, os.getenv("MODEL_CHAT", "gpt-3.5-turbo"))
        conversation_lines = await simulator.simulate_conversation(
            ctx.channel, topic, personality_indices, 6, self.bot
        )
        first = True
        for line in conversation_lines:
            for chunk in split_message(line, 2000):
                if first:
                    await ctx.respond(chunk)
                    first = False
                else:
                    await ctx.channel.send(chunk)
                await asyncio.sleep(3)

    # ── Sandwich ──────────────────────────────────────────────────────────────

    @bridge.bridge_command(description="Generate a random sandwich")
    async def sandwich(self, ctx):
        await ctx.defer()
        try:
            result = subprocess.run(
                ['python', 'funfunc/sandwich.py'], capture_output=True, text=True, check=True
            )
            await ctx.respond(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            await ctx.respond(f"Error generating sandwich: {e}")
            print(f"Error: {e}")


def setup(bot):
    bot.add_cog(FunCog(bot))
