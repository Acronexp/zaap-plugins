import asyncio
import logging
import random
import re
import time

import discord
from fuzzywuzzy import process
from redbot.core import Config, commands

logger = logging.getLogger("red.zaap-plugins.dotack")

class Dotack(commands.Cog):
    """Simulateur de Dotack"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        self.cache = {"putain_lvl": 1, "rdn_msg_cd": 0, "learner": {}}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild:
            if not message.author.bot:
                if message.guild.id == 204585334925819904:
                    content = message.content.lower()

                    if "pays" in content or "venu" in content:
                        rdn = random.randint(0, 8)
                        if 0 < rdn < 3:
                            regex = re.compile(r'(ce pays|:?venu:?)', re.DOTALL | re.IGNORECASE).findall(content)
                            if regex:
                                async with message.channel.typing():
                                    msg = ""
                                    types = []
                                    for obj in regex:
                                        if obj == "ce pays" and "pays" not in types:
                                            types.append("pays")
                                            lvl = self.cache["putain_lvl"]
                                            if lvl == 1:
                                                msg += "ce pays putain... "
                                            elif lvl == 2:
                                                msg += "CE PAYS PUTAIN... "
                                            elif lvl == 3:
                                                msg += "**CE PAYS PUTAIN** "
                                            self.cache["putain_lvl"] = self.cache["putain_lvl"] + 1 if self.cache["putain_lvl"] < 3 else 1
                                        elif obj in ["venu", ":venu:"] and "venu" not in types:
                                            types.append("venu")
                                            msg += random.choice([
                                                ":venu: ",
                                                "venu (sperme)... ",
                                                "péter pisser chier :venu:"
                                            ])
                                    wait = len(msg) / 10
                                    await asyncio.sleep(wait)
                                    await message.channel.send(msg)
                        elif rdn == 8:
                            emojis = ["🐵", "🐒"]
                            emoji = random.choice(emojis)
                            await message.add_reaction(emoji)

                    if "et" in content and not random.randint(0, 5):
                        if self.cache["rdn_msg_cd"] + 1200 > time.time():
                            async with message.channel.typing():
                                self.cache["rdn_msg_cd"] = time.time()
                                new = random.choice(["et venu :venu:", "et venu...", "et péter, pisser, chier et venu :venu:"])
                                msg = f"> {content}\n{new}"
                                wait = len(msg) / 10
                                await asyncio.sleep(wait)
                                await message.channel.send(msg)

                    if message.mentions:
                        if [user for user in message.mentions if user.id == 185443599524036608]:
                            learn = self.cache["learner"]
                            if content.lower() not in learn:
                                def check(msg: discord.Message):
                                    return msg.author.id == 185443599524036608
                                try:
                                    resp = await self.bot.wait_for("message", check=check, timeout=180)
                                except asyncio.TimeoutError:
                                    return
                                learn[content.lower()] = resp.content
                                return
                            proc = process.extractBests(content.lower(), list(self.cache["learner"].keys()))
                            bests = [p[0] for p in proc if p[1] >= 90]
                            if bests:
                                async with message.channel.typing():
                                    msg = random.choice(bests)
                                    wait = len(msg) / 10
                                    await asyncio.sleep(wait)
                                    await message.channel.send(msg)
                        elif [user for user in message.mentions if user.id == self.bot.user.id]:
                            proc = process.extractBests(content.lower(), list(self.cache["learner"].keys()))
                            bests = [p[0] for p in proc if p[1] >= 90]
                            if bests:
                                async with message.channel.typing():
                                    msg = random.choice(bests)
                                    wait = len(msg) / 10
                                    await asyncio.sleep(wait)
                                    await message.channel.send(msg)



