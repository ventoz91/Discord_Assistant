import discord
from discord.ext import commands
import aiohttp
from ragfunc.memory import async_store_document, async_count, async_clear_documents, async_clear_all


class RAGCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def _download_text(url: str) -> str | None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.text()
                return None

    # ── !learn / /learn ───────────────────────────────────────────────────────

    @commands.command(name="learn")
    async def learn_prefix(self, ctx, *, text: str = None):
        """Store text or an attached .txt file as a searchable document."""
        content, source = await self._resolve_learn_input(ctx.message.attachments, text, None)
        if content is None:
            await ctx.send("Provide some text or attach a `.txt` file.")
            return
        await self._do_learn(ctx, content, source)

    @discord.slash_command(name="learn", description="Store text or a file as a searchable document")
    async def learn_slash(
        self,
        ctx,
        text: discord.Option(str, "Text to store", required=False) = None,
        file: discord.Option(discord.Attachment, "Text file (.txt) to store", required=False) = None,
    ):
        await ctx.defer()
        content, source = await self._resolve_learn_input([], text, file)
        if content is None:
            await ctx.respond("Provide some text or attach a `.txt` file.")
            return
        await self._do_learn(ctx, content, source, slash=True)

    async def _resolve_learn_input(self, attachments, text, slash_file):
        if slash_file is not None:
            if not slash_file.filename.lower().endswith('.txt'):
                return None, None
            return await self._download_text(slash_file.url), slash_file.filename
        for att in attachments:
            if att.filename.lower().endswith('.txt'):
                return await self._download_text(att.url), att.filename
        if text:
            return text, "text"
        return None, None

    async def _do_learn(self, ctx, content: str, source: str, slash: bool = False):
        n = await async_store_document(ctx.channel.id, content, source=source)
        msg = f"Stored **{n}** chunk{'s' if n != 1 else ''} from `{source}` in memory."
        if slash:
            await ctx.respond(msg)
        else:
            await ctx.send(msg)

    # ── !memory / /memory ─────────────────────────────────────────────────────

    @commands.command(name="memory")
    async def memory_prefix(self, ctx):
        """Show memory stats for this channel."""
        await self._show_memory(ctx)

    @discord.slash_command(name="memory", description="Show memory stats for this channel")
    async def memory_slash(self, ctx):
        await ctx.defer()
        await self._show_memory(ctx, slash=True)

    async def _show_memory(self, ctx, slash: bool = False):
        stats = await async_count(ctx.channel.id)
        msg = f"**Memory stats for #{ctx.channel.name}**\nTotal stored chunks: `{stats['total']}`"
        if slash:
            await ctx.respond(msg)
        else:
            await ctx.send(msg)

    # ── !cleardocs / /cleardocs ───────────────────────────────────────────────

    @commands.command(name="cleardocs")
    async def cleardocs_prefix(self, ctx):
        """Remove all stored documents (keeps message history)."""
        await self._do_cleardocs(ctx)

    @discord.slash_command(name="cleardocs", description="Remove all stored documents from memory (keeps message history)")
    async def cleardocs_slash(self, ctx):
        await ctx.defer()
        await self._do_cleardocs(ctx, slash=True)

    async def _do_cleardocs(self, ctx, slash: bool = False):
        n = await async_clear_documents(ctx.channel.id)
        msg = f"Removed **{n}** document chunk{'s' if n != 1 else ''} from memory."
        if slash:
            await ctx.respond(msg)
        else:
            await ctx.send(msg)

    # ── !clearall (prefix only — too destructive for accidental slash) ────────

    @commands.command(name="clearall")
    @commands.has_permissions(manage_messages=True)
    async def clearall_prefix(self, ctx):
        """Wipe all memory (messages + documents) for this channel. Requires Manage Messages."""
        await async_clear_all(ctx.channel.id)
        await ctx.send("All memory cleared for this channel.")


def setup(bot):
    bot.add_cog(RAGCog(bot))
