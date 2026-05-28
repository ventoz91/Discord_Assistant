import discord
from discord.ext import commands
import aiohttp
import asyncio
import io
from ragfunc.memory import async_store_document, async_count, async_clear_documents, async_clear_all

TEXT_EXTENSIONS = {'.txt', '.py', '.md', '.js', '.ts', '.jsx', '.tsx', '.json', '.csv', '.yaml', '.yml', '.html', '.css', '.sh', '.toml', '.ini', '.cfg'}
PDF_EXTENSIONS = {'.pdf'}
ALL_SUPPORTED = TEXT_EXTENSIONS | PDF_EXTENSIONS


class RAGCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def _download_bytes(url: str) -> bytes | None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.read() if resp.status == 200 else None

    @staticmethod
    def _pdf_to_text(pdf_bytes: bytes) -> str:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(p for p in pages if p.strip())

    async def _file_to_text(self, url: str, filename: str) -> str | None:
        ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        raw = await self._download_bytes(url)
        if raw is None:
            return None
        if ext in PDF_EXTENSIONS:
            return await asyncio.to_thread(self._pdf_to_text, raw)
        try:
            return raw.decode('utf-8', errors='replace')
        except Exception:
            return None

    # ── !learn / /learn ───────────────────────────────────────────────────────

    @commands.command(name="learn")
    async def learn_prefix(self, ctx, *, text: str = None):
        """Store text or an attached file as a searchable document."""
        content, source = await self._resolve_learn_input(ctx.message.attachments, text, None)
        if content is None:
            exts = ', '.join(sorted(ALL_SUPPORTED))
            await ctx.send(f"Provide some text or attach a supported file ({exts}).")
            return
        await self._do_learn(ctx, content, source)

    @discord.slash_command(name="learn", description="Store text or a file as a searchable document")
    async def learn_slash(
        self,
        ctx,
        text: discord.Option(str, "Text to store", required=False) = None,
        file: discord.Option(discord.Attachment, "File to store (.txt, .py, .pdf, etc.)", required=False) = None,
    ):
        await ctx.defer()
        content, source = await self._resolve_learn_input([], text, file)
        if content is None:
            exts = ', '.join(sorted(ALL_SUPPORTED))
            await ctx.respond(f"Provide some text or attach a supported file ({exts}).")
            return
        await self._do_learn(ctx, content, source, slash=True)

    async def _resolve_learn_input(self, attachments, text, slash_file):
        if slash_file is not None:
            ext = '.' + slash_file.filename.rsplit('.', 1)[-1].lower() if '.' in slash_file.filename else ''
            if ext not in ALL_SUPPORTED:
                return None, None
            return await self._file_to_text(slash_file.url, slash_file.filename), slash_file.filename
        for att in attachments:
            ext = '.' + att.filename.rsplit('.', 1)[-1].lower() if '.' in att.filename else ''
            if ext in ALL_SUPPORTED:
                return await self._file_to_text(att.url, att.filename), att.filename
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
