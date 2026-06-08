import discord
import asyncio
import logging
import os
from gamefunc.minecraft import MinecraftServer

logger = logging.getLogger("bot.minecraft_panel")

_POLL_INTERVAL = 60  # seconds between auto-refresh polls

_STATUS = {
    'offline':  '🔴 Offline',
    'starting': '⏳ Starting…',
    'online':   '🟢 Online',
    'stopping': '⏹ Stopping…',
}

_CONNECT_ENV = {
    'vanilla': 'MINECRAFT_VANILLA_CONNECT_URL',
    'modded':  'MINECRAFT_MODDED_CONNECT_URL',
}

_BUTTON_RULES = {
    'start_vanilla':   ('vanilla', {'offline'}),
    'stop_vanilla':    ('vanilla', {'online'}),
    'restart_vanilla': ('vanilla', {'online'}),
    'start_modded':    ('modded',  {'offline'}),
    'stop_modded':     ('modded',  {'online'}),
    'restart_modded':  ('modded',  {'online'}),
}


class MinecraftPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=3600)
        self.server = MinecraftServer()
        self.states = {'vanilla': 'offline', 'modded': 'offline'}
        self.server_data: dict[str, dict | None] = {'vanilla': None, 'modded': None}
        self._message: discord.Message | None = None
        self._poll_task: asyncio.Task | None = None
        self._sync_buttons()

    async def start_auto_refresh(self, message: discord.Message):
        self._message = message
        await self.refresh_states(message)
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def _poll_loop(self):
        while not self.is_finished():
            await asyncio.sleep(_POLL_INTERVAL)
            if self.is_finished() or self._message is None:
                break
            try:
                await self.refresh_states(self._message)
            except Exception as e:
                logger.debug("Auto-refresh error: %s", e)

    async def on_timeout(self):
        if self._poll_task:
            self._poll_task.cancel()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _field_value(self, stype: str) -> str:
        state = self.states[stype]
        data = self.server_data[stype]
        if state != 'online' or not data:
            lines = [_STATUS[state]]
        else:
            lines = [_STATUS['online'],
                     f"{data['current']}/{data['maximum']} players"
                     + (f" · {data['tps']} TPS" if data['tps'] is not None else '')]
            if data['names']:
                lines.append(', '.join(data['names']))
        connect_url = os.getenv(_CONNECT_ENV[stype], '').strip()
        if connect_url:
            lines.append(f'Connect: {connect_url}')
        return '\n'.join(lines)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title='🎮 Minecraft Servers', color=0x2ECC71)
        embed.add_field(name='Vanilla', value=self._field_value('vanilla'), inline=True)
        embed.add_field(name='Modded',  value=self._field_value('modded'),  inline=True)
        return embed

    def _sync_buttons(self):
        for child in self.children:
            rule = _BUTTON_RULES.get(getattr(child, 'custom_id', ''))
            if rule:
                stype, allowed = rule
                child.disabled = self.states[stype] not in allowed

    async def _set(self, server_type: str, state: str, message: discord.Message):
        self.states[server_type] = state
        if state != 'online':
            self.server_data[server_type] = None
        self._sync_buttons()
        await message.edit(embed=self.build_embed(), view=self)

    async def _set_online(self, server_type: str, message: discord.Message):
        self.server_data[server_type] = await self.server.get_status(server_type)
        self.states[server_type] = 'online' if self.server_data[server_type] else 'offline'
        self._sync_buttons()
        await message.edit(embed=self.build_embed(), view=self)

    async def refresh_states(self, message: discord.Message):
        """Check actual server state via RCON and update the panel."""
        vanilla, modded = await asyncio.gather(
            self.server.get_status('vanilla'),
            self.server.get_status('modded'),
        )
        self.server_data['vanilla'] = vanilla
        self.server_data['modded']  = modded
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
        if not await self.server.start('vanilla'):
            await self._set('vanilla', 'offline', interaction.message)
            await interaction.followup.send('Failed to launch vanilla server — check SSH/Docker config.', ephemeral=True)
            return
        ready = await self.server.wait_until_ready('vanilla')
        if ready:
            await self._set_online('vanilla', interaction.message)
        else:
            await self._set('vanilla', 'offline', interaction.message)
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
        await self.server.start('vanilla')
        ready = await self.server.wait_until_ready('vanilla')
        if ready:
            await self._set_online('vanilla', interaction.message)
        else:
            await self._set('vanilla', 'offline', interaction.message)

    # ── Modded row (row=1) ────────────────────────────────────────────────────

    @discord.ui.button(label='Modded', style=discord.ButtonStyle.secondary, row=1, disabled=True, custom_id='label_modded')
    async def label_modded(self, button, interaction):
        pass

    @discord.ui.button(label='▶ Start',    style=discord.ButtonStyle.success,   row=1, custom_id='start_modded')
    async def start_modded(self, button, interaction):
        await interaction.response.defer()
        await self._set('modded', 'starting', interaction.message)
        if not await self.server.start('modded'):
            await self._set('modded', 'offline', interaction.message)
            await interaction.followup.send('Failed to launch modded server — check MINECRAFT_MODDED_DIR.', ephemeral=True)
            return
        ready = await self.server.wait_until_ready('modded')
        if ready:
            await self._set_online('modded', interaction.message)
        else:
            await self._set('modded', 'offline', interaction.message)
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
        await self.server.start('modded')
        ready = await self.server.wait_until_ready('modded')
        if ready:
            await self._set_online('modded', interaction.message)
        else:
            await self._set('modded', 'offline', interaction.message)

    # ── Refresh row (row=2) ───────────────────────────────────────────────────

    @discord.ui.button(label='🔄 Refresh', style=discord.ButtonStyle.secondary, row=2, custom_id='refresh_all')
    async def refresh_button(self, button, interaction):
        await interaction.response.defer()
        await self.refresh_states(interaction.message)
