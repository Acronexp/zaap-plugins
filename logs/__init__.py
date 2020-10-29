from .logs import Logs

def setup(bot):
    bot.add_cog(Logs(bot))