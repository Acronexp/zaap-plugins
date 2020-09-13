from .repost import Repost

def setup(bot):
    bot.add_cog(Repost(bot))