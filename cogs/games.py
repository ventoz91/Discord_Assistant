from discord.ext import commands
import asyncio
import gamefunc.tictactoe as tictactoe
from gamefunc.snake import SnakeGame


class GamesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def game(self, ctx, player_symbol: str = None):
        if self.bot.active_games.get(ctx.channel.id, False):
            await ctx.send("A game is already in progress in this channel.")
            return
        if player_symbol is None or player_symbol.upper() not in ['X', 'O']:
            await ctx.send("Please enter 'X' or 'O' to start the game. For example, `!game X`.")
            return
        self.bot.active_games[ctx.channel.id] = True
        try:
            await tictactoe.play_tic_tac_toe(ctx, self.bot, player_symbol)
        finally:
            self.bot.active_games[ctx.channel.id] = False

    @commands.command()
    async def snake(self, ctx):
        if self.bot.active_games.get(ctx.channel.id, False):
            await ctx.send("A game is already in progress in this channel.")
            return
        game = SnakeGame()
        self.bot.active_games[ctx.channel.id] = True
        print(self.bot.active_games)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        game_over = False
        while not game_over:
            await ctx.send("```" + game.render() + "```")
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            except asyncio.TimeoutError:
                await ctx.send("Game Timed Out")
                break
            content = msg.content.lower()
            if content == 'w':
                game.direction = (0, -1)
            elif content == 's':
                game.direction = (0, 1)
            elif content == 'a':
                game.direction = (-1, 0)
            elif content == 'd':
                game.direction = (1, 0)
            game_over = not game.move()

        await ctx.send("Game Over!")
        self.bot.active_games[ctx.channel.id] = False
        print(self.bot.active_games)


def setup(bot):
    bot.add_cog(GamesCog(bot))
