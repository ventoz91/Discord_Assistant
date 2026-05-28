from discord.ext import commands
import os
import asyncio
import subprocess
from funfunc.prompt import GPTSearchPrompt
from AIfunc.simulate import ConversationSimulator
from chatbotfunc.utils import split_message


class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def prompt(self, ctx, *, topic: str):
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            generator = GPTSearchPrompt(api_key, os.getenv("MODEL_CHAT", "gpt-3.5-turbo"))
            search_query = await generator.generate_search_query(topic)
            if search_query:
                await ctx.send(GPTSearchPrompt.construct_google_search_url(search_query))
            else:
                await ctx.send("Failed to generate search query.")
        except Exception as e:
            await ctx.send(f"Error: {e}")
            print(f"Error: {e}")

    @commands.command()
    async def simulate(self, ctx, *args):
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
        api_key = os.getenv("OPENAI_API_KEY")
        simulator = ConversationSimulator(api_key, os.getenv("MODEL_CHAT", "gpt-3.5-turbo"))
        conversation_lines = await simulator.simulate_conversation(
            ctx.channel, topic, personality_indices, 6, self.bot, self.bot.channel_file_contents
        )
        for line in conversation_lines:
            for chunk in split_message(line, 2000):
                await ctx.send(chunk)
                await asyncio.sleep(3)

    @commands.command()
    async def sandwich(self, ctx):
        try:
            result = subprocess.run(
                ['python', 'funfunc/sandwich.py'], capture_output=True, text=True, check=True
            )
            await ctx.send(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            await ctx.send(f"Error generating sandwich: {e}")
            print(f"Error: {e}")


def setup(bot):
    bot.add_cog(FunCog(bot))
