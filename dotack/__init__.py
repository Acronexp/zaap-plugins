from .dotack import Dotack

async def setup(bot):
    cog = Dotack(bot)
    bot.add_cog(cog)