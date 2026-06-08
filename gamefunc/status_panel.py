import asyncio
import os
import re
import discord
from gamefunc.minecraft import MinecraftServer
from gamefunc.satisfactory import SatisfactoryServer

# (hostname_env_var, default_display_name, internal_key)
_SERVERS = [
    ('MINECRAFT_VANILLA_HOSTNAME', 'Minecraft Vanilla', 'minecraft_vanilla'),
    ('MINECRAFT_MODDED_HOSTNAME',  'Minecraft Modded',  'minecraft_modded'),
    ('SATISFACTORY_HOSTNAME',      'Satisfactory',      'satisfactory'),
]


def _active_servers() -> list[tuple[str, str]]:
    """Returns (display_name, internal_key) for each server listed in STATUS_SERVERS.

    STATUS_SERVERS values are matched against the *_HOSTNAME env vars (case-insensitive).
    Internal keys (minecraft_vanilla, minecraft_modded, satisfactory) also accepted.
    If STATUS_SERVERS is unset, all configured servers are shown.
    """
    name_map = {}
    for env_var, default, key in _SERVERS:
        display = os.getenv(env_var, default)
        name_map[display.lower()] = (display, key)
        name_map[key] = (display, key)

    status_val = os.getenv('STATUS_SERVERS', '').strip()
    if not status_val:
        return [(os.getenv(ev, d), k) for ev, d, k in _SERVERS]

    result = []
    for entry in status_val.split(','):
        match = name_map.get(entry.strip().lower())
        if match:
            result.append(match)
    return result


def _parse_mc_players(response: str) -> tuple[int, int] | None:
    m = re.search(r'(\d+) of a max of (\d+)', response)
    return (int(m.group(1)), int(m.group(2))) if m else None


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
        active = _active_servers()

        _coros = {
            'minecraft_vanilla': lambda: self._mc.players('vanilla'),
            'minecraft_modded':  lambda: self._mc.players('modded'),
            'satisfactory':      lambda: self._sf.get_state(),
        }

        displays = [d for d, _ in active]
        keys     = [k for _, k in active]
        results  = await asyncio.gather(*(_coros[k]() for k in keys))

        embed = discord.Embed(title='🖥️ Game Servers', color=0x5865F2)

        for display, key, result in zip(displays, keys, results):
            if key in ('minecraft_vanilla', 'minecraft_modded'):
                parsed = _parse_mc_players(result)
                value = f"🟢 Online — {parsed[0]}/{parsed[1]} players" if parsed else '🔴 Offline'
                embed.add_field(name=display, value=value, inline=True)
            else:
                if result is None:
                    value = '🔴 Offline'
                elif not result['is_game_running']:
                    value = '🟡 Online — no save loaded'
                else:
                    value = (
                        f"🟢 Online — {result['num_players']}/{result['player_limit']} players\n"
                        f"Tier {result['tech_tier']} · {_fmt_duration(result['total_duration'])}"
                    )
                embed.add_field(name=display, value=value, inline=False)

        return embed

    @discord.ui.button(label='🔄 Refresh', style=discord.ButtonStyle.primary, custom_id='status_refresh')
    async def refresh(self, button, interaction):
        await interaction.response.defer()
        embed = await self.build_embed()
        await interaction.message.edit(embed=embed, view=self)
