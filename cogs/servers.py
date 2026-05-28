from discord.ext import commands
from gamefunc.minecraft_panel import MinecraftPanel
from gamefunc.valheim import ValheimServer, EnshroudedServer


class ServersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.valheim = ValheimServer()
        self.enshrouded = EnshroudedServer()

    @commands.command()
    async def minecraft(self, ctx):
        panel = MinecraftPanel()
        msg = await ctx.send(embed=panel.build_embed(), view=panel)
        await panel.refresh_states(msg)

    @commands.command()
    async def start_valheim(self, ctx):
        await ctx.send(self.valheim.start_server())

    @commands.command()
    async def stop_valheim(self, ctx):
        await ctx.send(self.valheim.stop_server())

    @commands.command()
    async def valheim_status(self, ctx):
        await ctx.send(self.valheim.server_status())

    @commands.command()
    async def start_enshrouded(self, ctx):
        await ctx.send(self.enshrouded.start_server())

    @commands.command()
    async def stop_enshrouded(self, ctx):
        await ctx.send(self.enshrouded.stop_server('enshrouded_server.exe'))


def setup(bot):
    bot.add_cog(ServersCog(bot))
