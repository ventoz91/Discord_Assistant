import discord
from gamefunc.satisfactory import SatisfactoryServer


def _fmt_duration(seconds: int) -> str:
    h, m = divmod(seconds // 60, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"

_STATUS = {
    'offline':  '🔴 Offline',
    'starting': '⏳ Starting…',
    'online':   '🟢 Online',
    'stopping': '⏹ Stopping…',
}

_KEEP = object()


class SatisfactoryPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=3600)
        self.server = SatisfactoryServer()
        self.state = 'offline'
        self.game_state: dict | None = None
        self._sync_buttons()

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title='🏭 Satisfactory Server', color=0xF4A223)
        embed.add_field(name='Status', value=_STATUS[self.state], inline=False)
        if self.state == 'online' and self.game_state:
            gs = self.game_state
            if not gs['is_game_running']:
                embed.add_field(name='', value='🟡 No save loaded', inline=False)
            else:
                embed.add_field(
                    name='Players',
                    value=f"{gs['num_players']} / {gs['player_limit']}",
                    inline=True,
                )
                embed.add_field(name='Tech Tier', value=f"Tier {gs['tech_tier']}", inline=True)
                embed.add_field(name='Play Time', value=_fmt_duration(gs['total_duration']), inline=True)
                if gs['session_name']:
                    embed.add_field(name='Session', value=gs['session_name'], inline=True)
                embed.add_field(name='Tick Rate', value=f"{gs['tick_rate']} TPS", inline=True)
                if gs['is_paused']:
                    embed.add_field(name='', value='⚠️ Game is paused', inline=False)
        return embed

    def _sync_buttons(self):
        for child in self.children:
            cid = getattr(child, 'custom_id', '')
            if cid == 'sf_start':
                child.disabled = self.state != 'offline'
            elif cid in {'sf_stop', 'sf_restart'}:
                child.disabled = self.state != 'online'

    async def _set(self, state: str, message: discord.Message, game_state=_KEEP):
        self.state = state
        if game_state is not _KEEP:
            self.game_state = game_state
        self._sync_buttons()
        await message.edit(embed=self.build_embed(), view=self)

    async def refresh_states(self, message: discord.Message):
        gs = await self.server.get_state()
        self.game_state = gs
        self.state = 'online' if gs is not None else 'offline'
        self._sync_buttons()
        await message.edit(embed=self.build_embed(), view=self)

    @discord.ui.button(label='▶ Start', style=discord.ButtonStyle.success, custom_id='sf_start')
    async def start(self, button, interaction):
        await interaction.response.defer()
        await self._set('starting', interaction.message)
        if not await self.server.start():
            await self._set('offline', interaction.message)
            await interaction.followup.send('Failed to start — check SSH/Docker config.', ephemeral=True)
            return
        ready = await self.server.wait_until_ready()
        gs = await self.server.get_state() if ready else None
        await self._set('online' if ready else 'offline', interaction.message, game_state=gs)
        if not ready:
            await interaction.followup.send('Timed out waiting for server API.', ephemeral=True)

    @discord.ui.button(label='⏹ Stop', style=discord.ButtonStyle.danger, custom_id='sf_stop')
    async def stop(self, button, interaction):
        await interaction.response.defer()
        await self._set('stopping', interaction.message)
        await self.server.stop()
        stopped = await self.server.wait_until_stopped()
        await self._set('offline' if stopped else 'online', interaction.message,
                        game_state=None if stopped else _KEEP)

    @discord.ui.button(label='↻ Restart', style=discord.ButtonStyle.secondary, custom_id='sf_restart')
    async def restart(self, button, interaction):
        await interaction.response.defer()
        await self._set('stopping', interaction.message)
        await self.server.stop()
        await self.server.wait_until_stopped()
        await self._set('starting', interaction.message, game_state=None)
        await self.server.start()
        ready = await self.server.wait_until_ready()
        gs = await self.server.get_state() if ready else None
        await self._set('online' if ready else 'offline', interaction.message, game_state=gs)
        if not ready:
            await interaction.followup.send('Timed out waiting for server API.', ephemeral=True)

    @discord.ui.button(label='🔄 Refresh', style=discord.ButtonStyle.primary, custom_id='sf_refresh')
    async def refresh(self, button, interaction):
        await interaction.response.defer()
        await self.refresh_states(interaction.message)
