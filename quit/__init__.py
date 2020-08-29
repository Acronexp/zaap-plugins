from .quit import Quit

def setup(bot):
    bot.add_cog(Quit(bot))