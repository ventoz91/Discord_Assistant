import asyncio
import logging

from discord.ext import commands, bridge

from chatbotfunc.reminders import (
    parse_duration, format_duration, add_reminder, list_reminders,
    cancel_reminder, reminder_loop,
)

logger = logging.getLogger("bot.reminders")


class RemindersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._loop_started = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._loop_started:
            return
        self._loop_started = True
        asyncio.create_task(reminder_loop(self.bot))

    @bridge.bridge_command(name="remind", description="Set a reminder: !remind 2h check the oven (units: s/m/h/d/w)")
    async def remind(self, ctx, duration: str, *, text: str):
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.respond("I couldn't read that duration — try `30m`, `2h`, `1d`, or `1h30m`.")
            return
        if seconds > 60 * 86400:
            await ctx.respond("That's more than 60 days out — I can't promise to remember that long.")
            return
        reminder = await asyncio.to_thread(
            add_reminder, ctx.channel.id, ctx.author.id, ctx.author.display_name, seconds, text
        )
        await ctx.respond(
            f"⏰ Got it — I'll remind you about \"{text}\" in {format_duration(seconds)} "
            f"(#{reminder['id']}, cancel with `!unremind {reminder['id']}`)."
        )

    @bridge.bridge_command(name="reminders", description="List your pending reminders")
    async def reminders(self, ctx):
        pending = await asyncio.to_thread(list_reminders, ctx.author.id)
        if not pending:
            await ctx.respond("You have no pending reminders.")
            return
        import time
        now = int(time.time())
        lines = [
            f"#{r['id']} — \"{r['text']}\" in {format_duration(max(r['due_ts'] - now, 0))}"
            for r in pending
        ]
        await ctx.respond("**Your reminders:**\n" + "\n".join(lines))

    @bridge.bridge_command(name="unremind", description="Cancel one of your reminders by number")
    async def unremind(self, ctx, reminder_id: int):
        cancelled = await asyncio.to_thread(cancel_reminder, reminder_id, ctx.author.id)
        if cancelled:
            await ctx.respond(f"Cancelled reminder #{reminder_id}: \"{cancelled['text']}\"")
        else:
            await ctx.respond(f"No reminder #{reminder_id} of yours — check `!reminders`.")


def setup(bot):
    bot.add_cog(RemindersCog(bot))
