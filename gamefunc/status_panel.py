import asyncio
import os
import discord
from gamefunc.minecraft import MinecraftServer
from gamefunc.satisfactory import SatisfactoryServer


def _enabled() -> set[str]:
    val = os.getenv('STATUS_SERVERS', 'minecraft_vanilla,minecraft_modded,satisfactory')
    return {s.strip() for s in val.split(',') if s.strip()}


def _fmt_duration(seconds: int) -> str:
    h, m = divmod(seconds // 60, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


class StatusPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=3600)
        self._mc = MinecraftServer()
        self._sf = SatisfactoryServer()

    async def build_embed(self) -> discord.Embed:
        enabled = _enabled()

        tasks = {}
        if 'minecraft_vanilla' in enabled:
            tasks['minecraft_vanilla'] = self._mc.is_running('vanilla')
        if 'minecraft_modded' in enabled:
            tasks['minecraft_modded'] = self._mc.is_running('modded')
        if 'satisfactory' in enabled:
            tasks['satisfactory'] = self._sf.get_state()

        results = dict(zip(tasks.keys(), await asyncio.gather(*tasks.values())))

        embed = discord.Embed(title='🖥️ Game Servers', color=0x5865F2)

        if 'minecraft_vanilla' in results:
            embed.add_field(
                name='Minecraft Vanilla',
                value='🟢 Online' if results['minecraft_vanilla'] else '🔴 Offline',
                inline=True,
            )
        if 'minecraft_modded' in results:
            embed.add_field(
                name='Minecraft Modded',
                value='🟢 Online' if results['minecraft_modded'] else '🔴 Offline',
                inline=True,
            )
        if 'satisfactory' in results:
            sf_state = results['satisfactory']
            if sf_state is None:
                sf_value = '🔴 Offline'
            elif not sf_state['is_game_running']:
                sf_value = '🟡 Online — no save loaded'
            else:
                sf_value = (
                    f"🟢 Online — {sf_state['num_players']}/{sf_state['player_limit']} players\n"
                    f"Tier {sf_state['tech_tier']} · {_fmt_duration(sf_state['total_duration'])}"
                )
            embed.add_field(name='Satisfactory', value=sf_value, inline=False)

        return embed

    @discord.ui.button(label='🔄 Refresh', style=discord.ButtonStyle.primary, custom_id='status_refresh')
    async def refresh(self, button, interaction):
        await interaction.response.defer()
        embed = await self.build_embed()
        await interaction.message.edit(embed=embed, view=self)
