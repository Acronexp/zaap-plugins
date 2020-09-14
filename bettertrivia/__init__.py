from .bettertrivia import BetterTrivia

def setup(bot):
    bot.add_cog(BetterTrivia(bot))