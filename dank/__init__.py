from .dank import Dank

async def setup(bot):
    cog = Dank(bot)
    bot.add_cog(cog)