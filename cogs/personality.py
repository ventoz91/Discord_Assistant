import discord
from discord.ext import commands
import os
import random
import tempfile


class PersonalityCog(commands.Cog):
    personality = discord.SlashCommandGroup("personality", "Personality commands")

    def __init__(self, bot):
        self.bot = bot

    # ── Prefix commands ───────────────────────────────────────────────────────

    @commands.command(name='new')
    async def new_prefix(self, ctx, *, new_personality: str):
        if self.bot.personality_manager.add_personality(new_personality):
            await ctx.send(f"New personality added: {new_personality}")
        else:
            await ctx.send("This personality already exists.")

    @commands.command(name='change')
    async def change_prefix(self, ctx, choice: int = None):
        personalities = self.bot.personality_manager.personalities
        if choice is not None and 1 <= choice <= len(personalities):
            self.bot.chatgpt_behaviour = personalities[choice - 1]
            await ctx.send(f"Behavior changed to: {self.bot.chatgpt_behaviour}")
        else:
            self.bot.chatgpt_behaviour = random.choice(personalities)
            await ctx.send(f"Random behavior selected! New behavior is: {self.bot.chatgpt_behaviour}")
        self.bot.personality_manager.set_active(self.bot.chatgpt_behaviour)

    @commands.command(name='list')
    async def list_prefix(self, ctx):
        personalities = self.bot.personality_manager.personalities
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as tmp:
            tmp_name = tmp.name
            for i, p in enumerate(personalities, start=1):
                tmp.write(f"{i}: {p}\n")
        with open(tmp_name, 'rb') as f:
            await ctx.send("Available Personalities:", file=discord.File(f, 'personalities_list.txt'))
        os.remove(tmp_name)

    @commands.command(name='pin')
    async def pin_prefix(self, ctx, choice: int = None):
        """Pin a personality to this channel. Uses current global personality if no index given."""
        personalities = self.bot.personality_manager.personalities
        if choice is not None and 1 <= choice <= len(personalities):
            descriptor = personalities[choice - 1]
        else:
            descriptor = self.bot.chatgpt_behaviour
        self.bot.personality_manager.set_channel_personality(ctx.channel.id, descriptor)
        await ctx.send(f"Pinned personality to #{ctx.channel.name}: {descriptor}")

    @commands.command(name='unpin')
    async def unpin_prefix(self, ctx):
        """Remove the pinned personality from this channel."""
        if self.bot.personality_manager.clear_channel_personality(ctx.channel.id):
            await ctx.send(f"Personality pin removed from #{ctx.channel.name}. Using global personality.")
        else:
            await ctx.send(f"No personality pinned to #{ctx.channel.name}.")

    # ── Slash commands ────────────────────────────────────────────────────────

    @personality.command(description="create new personality and add to file")
    async def new(self, ctx, new_personality: str = None):
        if new_personality is None:
            await ctx.respond("please specify a personality to add.")
            return
        if self.bot.personality_manager.add_personality(new_personality):
            await ctx.respond(f"New personality added: {new_personality}")
        else:
            await ctx.respond(f"personality '{new_personality}' already exists.")

    @personality.command(description="remove personality from list")
    async def remove(self, ctx, index: int = None):
        if index is None:
            await ctx.respond("please specify a personality to remove.")
            return
        removed = self.bot.personality_manager.remove_personality(index)
        if removed:
            await ctx.respond(f"Remove Personality: {removed}")
        else:
            await ctx.respond("Invalid index. Personality could not be found")

    @personality.command(description="change personality to one in file '/personality list' for options")
    async def change(self, ctx, choice: int = None):
        personalities = self.bot.personality_manager.personalities
        if choice is not None and 1 <= choice <= len(personalities):
            self.bot.chatgpt_behaviour = personalities[choice - 1]
        else:
            self.bot.chatgpt_behaviour = random.choice(personalities)
        self.bot.personality_manager.set_active(self.bot.chatgpt_behaviour)
        await ctx.respond(f"Behavior changed to: {self.bot.chatgpt_behaviour}")

    @personality.command(description="list personalities")
    async def list(self, ctx):
        personalities = self.bot.personality_manager.personalities
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as tmp:
            tmp_name = tmp.name
            for i, p in enumerate(personalities, start=1):
                tmp.write(f"{i}: {p}\n")
        with open(tmp_name, 'rb') as f:
            await ctx.respond("Available Personalities:", file=discord.File(f, 'personalities_list.txt'))
        os.remove(tmp_name)

    @personality.command(description="pin a personality to this channel permanently")
    async def pin(self, ctx, choice: discord.Option(int, "Personality number from /personality list", required=False) = None):
        personalities = self.bot.personality_manager.personalities
        if choice is not None and 1 <= choice <= len(personalities):
            descriptor = personalities[choice - 1]
        else:
            descriptor = self.bot.chatgpt_behaviour
        self.bot.personality_manager.set_channel_personality(ctx.channel.id, descriptor)
        await ctx.respond(f"Pinned personality to #{ctx.channel.name}: {descriptor}")

    @personality.command(description="remove the pinned personality from this channel")
    async def unpin(self, ctx):
        if self.bot.personality_manager.clear_channel_personality(ctx.channel.id):
            await ctx.respond(f"Personality pin removed from #{ctx.channel.name}. Using global personality.")
        else:
            await ctx.respond(f"No personality pinned to #{ctx.channel.name}.")


def setup(bot):
    bot.add_cog(PersonalityCog(bot))
