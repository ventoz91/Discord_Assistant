import logging
import os

import discord
from discord.ext import commands, bridge
from gamefunc.minecraft_panel import MinecraftPanel
from gamefunc.satisfactory_panel import SatisfactoryPanel
from gamefunc.status_panel import StatusPanel
from gamefunc.emucoach import EmucoachServer
from gamefunc.dragonwilds import DragonwildsServer
from gamefunc.dragonwilds_panel import DragonwildsPanel

logger = logging.getLogger("bot.servers")


def _connect_line() -> str:
    connect = os.getenv('DRAGONWILDS_CONNECT_URL', '').strip()
    return f'\nConnect: `{connect}`' if connect else ''


async def _notify_dragonwilds_channel(bot, text: str):
    """Cross-post to DRAGONWILDS_CHANNEL_ID when start/stop happens via a
    command rather than the persistent panel's own buttons — the panel already
    visibly updates in that channel for its own button clicks, so this only
    fires from the prefix/slash paths to give the channel visibility into
    actions taken elsewhere."""
    channel_id = os.getenv('DRAGONWILDS_CHANNEL_ID', '').strip()
    if not channel_id:
        return
    try:
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send(text)
    except Exception:
        logger.debug("dragonwilds channel notify failed", exc_info=True)


class ServersCog(commands.Cog):
    emucoach = discord.SlashCommandGroup("emucoach", "EmuCoach WoW server commands")
    dragonwilds = discord.SlashCommandGroup("dragonwilds", "RuneScape: Dragonwilds server commands")

    def __init__(self, bot):
        self.bot = bot
        self._emucoach = EmucoachServer()
        self._dragonwilds = DragonwildsServer()
        self._dragonwilds_panel_posted = False

    @commands.Cog.listener()
    async def on_ready(self):
        # Re-fires on gateway re-identify; guard so we don't repost/duplicate
        # the persistent panel on every reconnect.
        if self._dragonwilds_panel_posted:
            return
        channel_id = os.getenv('DRAGONWILDS_CHANNEL_ID', '').strip()
        if not channel_id:
            return
        self._dragonwilds_panel_posted = True
        try:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                channel = await self.bot.fetch_channel(int(channel_id))
            panel = DragonwildsPanel(persistent=True)
            self.bot.add_view(panel)  # registers custom_ids so buttons survive restarts
            message = await self._find_existing_panel(channel)
            if message:
                await message.edit(embed=panel.build_embed(), view=panel)
            else:
                message = await channel.send(embed=panel.build_embed(), view=panel)
            await panel.start_auto_refresh(message)
        except Exception:
            logger.warning("Failed to post/refresh Dragonwilds panel", exc_info=True)

    async def _find_existing_panel(self, channel) -> discord.Message | None:
        """Looks for a panel this bot already posted in the channel (by title),
        so a restart edits the existing message instead of spamming a new one
        every time. No persisted message-ID store — recent history is enough
        and avoids adding another data/*.json file for a single message."""
        try:
            async for msg in channel.history(limit=20):
                if msg.author.id == self.bot.user.id and msg.embeds:
                    if msg.embeds[0].title == '🐉 RuneScape: Dragonwilds':
                        return msg
        except Exception:
            logger.debug("panel history search failed", exc_info=True)
        return None

    # ── Minecraft ─────────────────────────────────────────────────────────────

    @bridge.bridge_command(description="Open the Minecraft server management panel")
    async def minecraft(self, ctx):
        panel = MinecraftPanel()
        msg = await ctx.channel.send(embed=panel.build_embed(), view=panel)
        await panel.start_auto_refresh(msg)
        if hasattr(ctx, 'interaction') and ctx.interaction:
            await ctx.respond("Panel opened above.", ephemeral=True)

    # ── Status overview ──────────────────────────────────────────────────────

    @bridge.bridge_command(description="Show live status for all game servers")
    async def status(self, ctx):
        await ctx.defer()
        panel = StatusPanel()
        embed = await panel.build_embed()
        await ctx.respond(embed=embed, view=panel)

    # ── Web panel ─────────────────────────────────────────────────────────────

    @bridge.bridge_command(description="Get the link to the web admin panel")
    async def panel(self, ctx):
        url = os.getenv('WEBPANEL_URL', '').strip()
        if not url:
            await ctx.respond("Web panel URL isn't configured — set WEBPANEL_URL in .env.", ephemeral=True)
            return
        await ctx.respond(f"🌐 Game server panel: {url}", ephemeral=True)

    # ── Satisfactory ─────────────────────────────────────────────────────────

    @bridge.bridge_command(description="Open the Satisfactory server management panel")
    async def satisfactory(self, ctx):
        panel = SatisfactoryPanel()
        msg = await ctx.channel.send(embed=panel.build_embed(), view=panel)
        await panel.refresh_states(msg)
        if hasattr(ctx, 'interaction') and ctx.interaction:
            await ctx.respond("Panel opened above.", ephemeral=True)

    # ── EmuCoach prefix commands ──────────────────────────────────────────────

    @commands.command(name="start_emucoach")
    async def start_emucoach_prefix(self, ctx):
        await ctx.send(await self._emucoach.start_server())

    @commands.command(name="stop_emucoach")
    async def stop_emucoach_prefix(self, ctx):
        await ctx.send(await self._emucoach.stop_server())

    @commands.command(name="emucoach_status")
    async def emucoach_status_prefix(self, ctx):
        await ctx.send(await self._emucoach.server_status())

    # ── EmuCoach slash commands ───────────────────────────────────────────────

    @emucoach.command(name="start", description="Start the EmuCoach WoW server (database, auth, world)")
    async def emucoach_start(self, ctx):
        await ctx.defer()
        await ctx.respond(await self._emucoach.start_server())

    @emucoach.command(name="stop", description="Stop the EmuCoach WoW server")
    async def emucoach_stop(self, ctx):
        await ctx.defer()
        await ctx.respond(await self._emucoach.stop_server())

    @emucoach.command(name="status", description="Check the EmuCoach WoW server status")
    async def emucoach_status_slash(self, ctx):
        await ctx.defer()
        await ctx.respond(await self._emucoach.server_status())

    # ── Dragonwilds ───────────────────────────────────────────────────────────

    async def _dragonwilds_start(self) -> str:
        if not os.getenv('DRAGONWILDS_SSH_HOST', ''):
            return "⚙️ Dragonwilds isn't configured — set DRAGONWILDS_SSH_HOST in .env."
        if await self._dragonwilds.is_running():
            return f"🟢 Dragonwilds is already online.{_connect_line()}"
        if not await self._dragonwilds.start():
            return "❌ Couldn't start Dragonwilds — check the bot log for SSH/Docker errors."
        ready = await self._dragonwilds.wait_until_ready()
        if not ready:
            return "🟡 Dragonwilds is starting but hasn't come online yet — check `/dragonwilds status` in a minute."
        await _notify_dragonwilds_channel(self.bot, f"🟢 Dragonwilds started.{_connect_line()}")
        return f"🟢 Dragonwilds started.{_connect_line()}"

    async def _dragonwilds_stop(self) -> str:
        if not os.getenv('DRAGONWILDS_SSH_HOST', ''):
            return "⚙️ Dragonwilds isn't configured — set DRAGONWILDS_SSH_HOST in .env."
        if not await self._dragonwilds.is_running():
            return "🔴 Dragonwilds is already stopped."
        await self._dragonwilds.stop()
        stopped = await self._dragonwilds.wait_until_stopped()
        if not stopped:
            return "🟡 Stop requested but Dragonwilds hasn't gone down yet — check `/dragonwilds status` in a minute."
        await _notify_dragonwilds_channel(self.bot, "🔴 Dragonwilds stopped.")
        return "🔴 Dragonwilds stopped."

    async def _dragonwilds_status(self) -> str:
        if not os.getenv('DRAGONWILDS_SSH_HOST', ''):
            return "⚙️ Dragonwilds isn't configured — set DRAGONWILDS_SSH_HOST in .env."
        running = await self._dragonwilds.is_running()
        return f"🟢 Online.{_connect_line()}" if running else "🔴 Offline."

    @commands.command(name="start_dragonwilds")
    async def start_dragonwilds_prefix(self, ctx):
        await ctx.send(await self._dragonwilds_start())

    @commands.command(name="stop_dragonwilds")
    async def stop_dragonwilds_prefix(self, ctx):
        await ctx.send(await self._dragonwilds_stop())

    @commands.command(name="dragonwilds_status")
    async def dragonwilds_status_prefix(self, ctx):
        await ctx.send(await self._dragonwilds_status())

    @dragonwilds.command(name="start", description="Start the Dragonwilds dedicated server")
    async def dragonwilds_start(self, ctx):
        await ctx.defer()
        await ctx.respond(await self._dragonwilds_start())

    @dragonwilds.command(name="stop", description="Stop the Dragonwilds dedicated server")
    async def dragonwilds_stop(self, ctx):
        await ctx.defer()
        await ctx.respond(await self._dragonwilds_stop())

    @dragonwilds.command(name="status", description="Check the Dragonwilds server status")
    async def dragonwilds_status_slash(self, ctx):
        await ctx.defer()
        await ctx.respond(await self._dragonwilds_status())


def setup(bot):
    bot.add_cog(ServersCog(bot))
