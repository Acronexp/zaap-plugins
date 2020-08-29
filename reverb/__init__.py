from .reverb import Reverb

def setup(bot):
    bot.add_cog(Reverb(bot))