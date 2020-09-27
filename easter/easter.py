import logging

from redbot.core import commands

logger = logging.getLogger("red.zaap-plugins.easter")

class Easter(commands.Cog):
    """???""" # Si vous lisez ceci vous avez découvert, sans trop de difficultés (vu le nom), le module dédié aux easter eggs généraux

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        content = message.content
        if "elon musk" in content.lower() or "léon musque" in content.lower():
            try:
                await message.add_reaction("😡")
            except:
                pass
        if content.lower() == "quoi":
            try:
                async for msg in message.channel.history(limit=10, before=message):
                    if msg.author != message.author:
                        await message.channel.send(f"📢 {msg.author.name} a dit **{msg.content}**")
                        return
            except:
                pass
        if "la boucle" in content.lower():
            try:
                await message.add_reaction("🙏")
            except:
                pass
