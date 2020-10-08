from .october import October

async def setup(bot):
    cog = October(bot)
    bot.add_cog(cog)