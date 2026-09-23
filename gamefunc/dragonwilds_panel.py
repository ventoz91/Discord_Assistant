import discord
import os
import asyncio
import logging
from gamefunc.dragonwilds import DragonwildsServer

logger = logging.getLogger("bot.dragonwilds_panel")

_POLL_INTERVAL = 60  # seconds between auto-refresh polls

_STATUS = {
    'offline':  '🔴 Offline',
    'starting': '⏳ Starting…',
    'online':   '🟢 Online',
    'stopping': '⏹ Stopping…',
}


class DragonwildsPanel(discord.ui.View):
    """Start/stop/status panel for the Dragonwilds server. Single instance,
    single row of buttons (unlike MinecraftPanel's vanilla/modded split) —
    there's only one Dragonwilds server.

    persistent=True (used for the auto-posted panel in DRAGONWILDS_CHANNEL_ID)
    sets timeout=None so the buttons never stop working, and relies on the
    caller registering this view with bot.add_view() so it keeps handling
    interactions across bot restarts. persistent=False (used by the manual
    /dragonwilds command, matching Minecraft/Satisfactory) times out after an
    hour like the other on-demand panels.
    """

    def __init__(self, persistent: bool = False):
        super().__init__(timeout=None if persistent else 3600)
        self.server = DragonwildsServer()
        self.state = 'offline'
        self._message: discord.Message | None = None
        self._poll_task: asyncio.Task | None = None
        self._sync_buttons()

    async def start_auto_refresh(self, message: discord.Message):
        self._message = message
        await self.refresh_state(message)
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def _poll_loop(self):
        while not self.is_finished():
            await asyncio.sleep(_POLL_INTERVAL)
            if self.is_finished() or self._message is None:
                break
            try:
                await self.refresh_state(self._message)
            except Exception as e:
                logger.debug("Auto-refresh error: %s", e)

    async def on_timeout(self):
        if self._poll_task:
            self._poll_task.cancel()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _field_value(self) -> str:
        lines = [_STATUS[self.state]]
        connect = os.getenv('DRAGONWILDS_CONNECT_URL', '').strip()
        if connect and self.state == 'online':
            lines.append(f'Connect: `{connect}`')
        return '\n'.join(lines)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title='🐉 RuneScape: Dragonwilds', color=0x8B4513)
        embed.add_field(name='Status', value=self._field_value(), inline=False)
        return embed

    def _sync_buttons(self):
        for child in self.children:
            cid = getattr(child, 'custom_id', '')
            if cid == 'dw_start':
                child.disabled = self.state not in ('offline',)
            elif cid == 'dw_stop':
                child.disabled = self.state not in ('online',)

    async def _set(self, state: str, message: discord.Message):
        self.state = state
        self._sync_buttons()
        await message.edit(embed=self.build_embed(), view=self)

    async def refresh_state(self, message: discord.Message):
        running = await self.server.is_running()
        self.state = 'online' if running else 'offline'
        self._sync_buttons()
        await message.edit(embed=self.build_embed(), view=self)

    # ── buttons ───────────────────────────────────────────────────────────────

    @discord.ui.button(label='▶ Start', style=discord.ButtonStyle.success, custom_id='dw_start')
    async def start_button(self, button, interaction):
        await interaction.response.defer()
        await self._set('starting', interaction.message)
        if not await self.server.start():
            await self._set('offline', interaction.message)
            await interaction.followup.send('Failed to start — check SSH/Docker config.', ephemeral=True)
            return
        ready = await self.server.wait_until_ready()
        if ready:
            await self._set('online', interaction.message)
        else:
            await self._set('offline', interaction.message)
            await interaction.followup.send('Dragonwilds timed out waiting to come online.', ephemeral=True)

    @discord.ui.button(label='⏹ Stop', style=discord.ButtonStyle.danger, custom_id='dw_stop')
    async def stop_button(self, button, interaction):
        await interaction.response.defer()
        await self._set('stopping', interaction.message)
        await self.server.stop()
        stopped = await self.server.wait_until_stopped()
        await self._set('offline' if stopped else 'online', interaction.message)

    @discord.ui.button(label='🔄 Refresh', style=discord.ButtonStyle.secondary, custom_id='dw_refresh')
    async def refresh_button(self, button, interaction):
        await interaction.response.defer()
        await self.refresh_state(interaction.message)
