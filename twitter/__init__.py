from .twitter import Twitter

def setup(bot):
    bot.add_cog(Twitter(bot))