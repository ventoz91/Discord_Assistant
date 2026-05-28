import discord
import asyncio
from gamefunc.minecraft import MinecraftServer

_STATUS = {
    'offline':  '🔴 Offline',
    'starting': '⏳ Starting…',
    'online':   '🟢 Online',
    'stopping': '⏹ Stopping…',
}

_BUTTON_RULES = {
    'start_vanilla':   ('vanilla', {'offline'}),
    'stop_vanilla':    ('vanilla', {'online'}),
    'restart_vanilla': ('vanilla', {'online'}),
    'players_vanilla': ('vanilla', {'online'}),
    'start_modded':    ('modded',  {'offline'}),
    'stop_modded':     ('modded',  {'online'}),
    'restart_modded':  ('modded',  {'online'}),
    'players_modded':  ('modded',  {'online'}),
}


class MinecraftPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=3600)
        self.server = MinecraftServer()
        self.states = {'vanilla': 'offline', 'modded': 'offline'}
        self._sync_buttons()

    # ── helpers ───────────────────────────────────────────────────────────────

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title='🎮 Minecraft Servers', color=0x2ECC71)
        embed.add_field(name='Vanilla', value=_STATUS[self.states['vanilla']], inline=True)
        embed.add_field(name='Modded',  value=_STATUS[self.states['modded']],  inline=True)
        return embed

    def _sync_buttons(self):
        for child in self.children:
            rule = _BUTTON_RULES.get(getattr(child, 'custom_id', ''))
            if rule:
                stype, allowed = rule
                child.disabled = self.states[stype] not in allowed

    async def _set(self, server_type: str, state: str, message: discord.Message):
        self.states[server_type] = state
        self._sync_buttons()
        await message.edit(embed=self.build_embed(), view=self)

    async def refresh_states(self, message: discord.Message):
        """Check actual server state via RCON and update the panel."""
        vanilla = await self.server.is_running('vanilla')
        modded  = await self.server.is_running('modded')
        self.states['vanilla'] = 'online' if vanilla else 'offline'
        self.states['modded']  = 'online' if modded  else 'offline'
        self._sync_buttons()
        await message.edit(embed=self.build_embed(), view=self)

    # ── Vanilla row (row=0) ───────────────────────────────────────────────────

    @discord.ui.button(label='Vanilla', style=discord.ButtonStyle.secondary, row=0, disabled=True, custom_id='label_vanilla')
    async def label_vanilla(self, button, interaction):
        pass

    @discord.ui.button(label='▶ Start',    style=discord.ButtonStyle.success,   row=0, custom_id='start_vanilla')
    async def start_vanilla(self, button, interaction):
        await interaction.response.defer()
        await self._set('vanilla', 'starting', interaction.message)
        if not self.server.start('vanilla'):
            await self._set('vanilla', 'offline', interaction.message)
            await interaction.followup.send('Failed to launch vanilla server — check MINECRAFT_VANILLA_DIR.', ephemeral=True)
            return
        ready = await self.server.wait_until_ready('vanilla')
        await self._set('vanilla', 'online' if ready else 'offline', interaction.message)
        if not ready:
            await interaction.followup.send('Vanilla timed out waiting for RCON.', ephemeral=True)

    @discord.ui.button(label='⏹ Stop',     style=discord.ButtonStyle.danger,    row=0, custom_id='stop_vanilla')
    async def stop_vanilla(self, button, interaction):
        await interaction.response.defer()
        await self._set('vanilla', 'stopping', interaction.message)
        await self.server.stop('vanilla')
        stopped = await self.server.wait_until_stopped('vanilla')
        await self._set('vanilla', 'offline' if stopped else 'online', interaction.message)

    @discord.ui.button(label='↻ Restart',  style=discord.ButtonStyle.secondary, row=0, custom_id='restart_vanilla')
    async def restart_vanilla(self, button, interaction):
        await interaction.response.defer()
        await self._set('vanilla', 'stopping', interaction.message)
        await self.server.stop('vanilla')
        await self.server.wait_until_stopped('vanilla')
        await self._set('vanilla', 'starting', interaction.message)
        self.server.start('vanilla')
        ready = await self.server.wait_until_ready('vanilla')
        await self._set('vanilla', 'online' if ready else 'offline', interaction.message)

    @discord.ui.button(label='👥 Players', style=discord.ButtonStyle.primary,   row=0, custom_id='players_vanilla')
    async def players_vanilla(self, button, interaction):
        await interaction.response.defer()
        result = await self.server.players('vanilla')
        await interaction.followup.send(f'**Vanilla:** {result}', ephemeral=True)

    # ── Modded row (row=1) ────────────────────────────────────────────────────

    @discord.ui.button(label='Modded', style=discord.ButtonStyle.secondary, row=1, disabled=True, custom_id='label_modded')
    async def label_modded(self, button, interaction):
        pass

    @discord.ui.button(label='▶ Start',    style=discord.ButtonStyle.success,   row=1, custom_id='start_modded')
    async def start_modded(self, button, interaction):
        await interaction.response.defer()
        await self._set('modded', 'starting', interaction.message)
        if not self.server.start('modded'):
            await self._set('modded', 'offline', interaction.message)
            await interaction.followup.send('Failed to launch modded server — check MINECRAFT_MODDED_DIR.', ephemeral=True)
            return
        ready = await self.server.wait_until_ready('modded')
        await self._set('modded', 'online' if ready else 'offline', interaction.message)
        if not ready:
            await interaction.followup.send('Modded timed out waiting for RCON.', ephemeral=True)

    @discord.ui.button(label='⏹ Stop',     style=discord.ButtonStyle.danger,    row=1, custom_id='stop_modded')
    async def stop_modded(self, button, interaction):
        await interaction.response.defer()
        await self._set('modded', 'stopping', interaction.message)
        await self.server.stop('modded')
        stopped = await self.server.wait_until_stopped('modded')
        await self._set('modded', 'offline' if stopped else 'online', interaction.message)

    @discord.ui.button(label='↻ Restart',  style=discord.ButtonStyle.secondary, row=1, custom_id='restart_modded')
    async def restart_modded(self, button, interaction):
        await interaction.response.defer()
        await self._set('modded', 'stopping', interaction.message)
        await self.server.stop('modded')
        await self.server.wait_until_stopped('modded')
        await self._set('modded', 'starting', interaction.message)
        self.server.start('modded')
        ready = await self.server.wait_until_ready('modded')
        await self._set('modded', 'online' if ready else 'offline', interaction.message)

    @discord.ui.button(label='👥 Players', style=discord.ButtonStyle.primary,   row=1, custom_id='players_modded')
    async def players_modded(self, button, interaction):
        await interaction.response.defer()
        result = await self.server.players('modded')
        await interaction.followup.send(f'**Modded:** {result}', ephemeral=True)
