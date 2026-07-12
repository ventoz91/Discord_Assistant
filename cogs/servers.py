import discord
from discord.ext import commands, bridge
from gamefunc.minecraft_panel import MinecraftPanel
from gamefunc.satisfactory_panel import SatisfactoryPanel
from gamefunc.status_panel import StatusPanel
from gamefunc.valheim import ValheimServer, EnshroudedServer
from gamefunc.emucoach import EmucoachServer


class ServersCog(commands.Cog):
    valheim = discord.SlashCommandGroup("valheim", "Valheim server commands")
    enshrouded = discord.SlashCommandGroup("enshrouded", "Enshrouded server commands")
    emucoach = discord.SlashCommandGroup("emucoach", "EmuCoach WoW server commands")

    def __init__(self, bot):
        self.bot = bot
        self._valheim = ValheimServer()
        self._enshrouded = EnshroudedServer()
        self._emucoach = EmucoachServer()

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

    # ── Satisfactory ─────────────────────────────────────────────────────────

    @bridge.bridge_command(description="Open the Satisfactory server management panel")
    async def satisfactory(self, ctx):
        panel = SatisfactoryPanel()
        msg = await ctx.channel.send(embed=panel.build_embed(), view=panel)
        await panel.refresh_states(msg)
        if hasattr(ctx, 'interaction') and ctx.interaction:
            await ctx.respond("Panel opened above.", ephemeral=True)

    # ── Valheim prefix commands ───────────────────────────────────────────────

    @commands.command(name="start_valheim")
    async def start_valheim_prefix(self, ctx):
        await ctx.send(self._valheim.start_server())

    @commands.command(name="stop_valheim")
    async def stop_valheim_prefix(self, ctx):
        await ctx.send(self._valheim.stop_server())

    @commands.command(name="valheim_status")
    async def valheim_status_prefix(self, ctx):
        await ctx.send(self._valheim.server_status())

    # ── Valheim slash commands ────────────────────────────────────────────────

    @valheim.command(name="start", description="Start the Valheim dedicated server")
    async def valheim_start(self, ctx):
        await ctx.respond(self._valheim.start_server())

    @valheim.command(name="stop", description="Stop the Valheim dedicated server")
    async def valheim_stop(self, ctx):
        await ctx.respond(self._valheim.stop_server())

    @valheim.command(name="status", description="Check Valheim server status")
    async def valheim_status_slash(self, ctx):
        await ctx.respond(self._valheim.server_status())

    # ── Enshrouded prefix commands ────────────────────────────────────────────

    @commands.command(name="start_enshrouded")
    async def start_enshrouded_prefix(self, ctx):
        await ctx.send(self._enshrouded.start_server())

    @commands.command(name="stop_enshrouded")
    async def stop_enshrouded_prefix(self, ctx):
        await ctx.send(self._enshrouded.stop_server('enshrouded_server.exe'))

    # ── Enshrouded slash commands ─────────────────────────────────────────────

    @enshrouded.command(name="start", description="Start the Enshrouded dedicated server")
    async def enshrouded_start(self, ctx):
        await ctx.respond(self._enshrouded.start_server())

    @enshrouded.command(name="stop", description="Stop the Enshrouded dedicated server")
    async def enshrouded_stop(self, ctx):
        await ctx.respond(self._enshrouded.stop_server('enshrouded_server.exe'))

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


def setup(bot):
    bot.add_cog(ServersCog(bot))
