from .bettertrivia import BetterTrivia

async def setup(bot):
    cog = BetterTrivia(bot)
    await cog.initialize()
    bot.add_cog(cog)