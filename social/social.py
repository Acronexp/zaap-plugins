from redbot.core import commands
import asyncio
import random
import time
from datetime import datetime
import discord

from redbot.core import Config, checks, commands

__version__ = "1.0.0"

ACTIVITY_TYPES = {
    discord.ActivityType.playing: "Joue",
    discord.ActivityType.watching: "Regarde",
    discord.ActivityType.listening: "Écoute",
}

STATUS_COLORS = {
    discord.Status.online: 0x40AC7B,
    discord.Status.idle: 0xFAA61A,
    discord.Status.dnd: 0xF04747,
    discord.Status.offline: 0x747F8D
}

class Social(commands.Cog):
    """Fonctionnalités sociales supplémentaires"""

    def __init__(self):
        super().__init__()
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        default_member = {"first_record": 0,
                          "names": [],
                          "nicknames": [],
                          "cons_days": [],
                          "logs": []} # Paramètres des membres dans le serveur
        default_user = {"games": [],
                        "disabled": False} # Paramètres des utilisateurs indépendamment du serveur
        # TODO: Détection & tri des jeux joués ^

        self.config.register_member(**default_member)
        self.config.register_user(**default_user)

    def is_streaming(self, user: discord.Member):
        if user.activities:
            return any([activity.type is discord.ActivityType.streaming for activity in user.activities])
        return False

    def get_custom_status(self, user: discord.Member):
        if user.activities:
            for activity in user.activities:
                if isinstance(activity, discord.CustomActivity):
                    if activity.name:
                        return activity.name
        return ""

    @commands.command(aliases=["uc"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def usercard(self, ctx, target: discord.Member = None):
        """Renvoie une carte de membre affichant diverses infos sur celui-ci

        [target] = si la carte affichée doit être celui du membre visé"""
        if not target: target = ctx.author
        guild_data = await self.config.member(target)

        created_since, joined_since = (datetime.now() - target.created_at).days, (datetime.now() - target.joined_at).day
        booster_since = (datetime.now() - target.premium_since).days if target.premium_since else False
        voice_channel = target.voice.channel.mention if target.voice else None

        embed_color = STATUS_COLORS[target.status] if not self.is_streaming(target) else 0x6438AA
        flames, last_msg = len(guild_data.cons_days()), guild_data.cons_days()[-1] or time.strftime("%d/%m/%Y", time.localtime())
        first_record = datetime.fromtimestamp(guild_data.first_record())
        record_since = (datetime.now() - first_record).days
        logs = guild_data.logs()[::-1]
        names, nicknames = guild_data.names()[::-1], guild_data.nicknames()[::-1]

        em = discord.Embed(description=self.get_custom_status(target), color=embed_color)
        em.title = target.name if not target.nick else "{} « {} »".format(target.name, target.nick)
        em.set_thumbnail(url=target.avatar_url)

        presence_txt = "**Création du compte** • {} · **{}**j\n" \
                       "**Arrivée sur le serveur** • {} · **{}**j\n" \
                       "**Première trace** • {} · **{}**j\n" \
                       "**Dernier message** • {} · \🔥{}".format(target.created_at.strftime("%d/%m/%Y"), created_since,
                                                                   target.joined_at.strftime("%d/%m/%Y"), joined_since,
                                                                   first_record.strftime("%d/%m/%Y"), record_since,
                                                                   last_msg, flames)
        if booster_since:
            presence_txt += "\n**Booste depuis** • {} · **{}**j".format(target.premium_since.strftime("%d/%m/%Y"), booster_since)
        em.add_field(name="Présence", value=presence_txt, inline=False)
        em.add_field(name="Rôles", value=" ".join(["`" + role.name + "`" for role in target.roles if not role.is_default()]) or "*Aucun*")
        em.set_footer(text="ID: " + target.id, icon_url="https://ponyvilleplaza.com/files/img/boost.png" if booster_since else "")

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def avatar(self, ctx, user: discord.User, size: int = 1024):
        """Affiche l'avatar de l'utilisateur visé

        [size] = Modifie la taille de l'avatar à afficher (def. 1024*1024)"""
        avatar_url = str(user.avatar_url_as(size=size))
        em = discord.Embed(title=str(user), color=user.color, description="<" + avatar_url + ">")
        em.set_image(url=avatar_url)
        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def games(self, ctx, target: discord.Member = None):
        """Affiche les jeux détectés comme étant possédés

        [target] = si les jeux affichés doivent être ceux du membre visé"""
        if not target: target = ctx.author

    @commands.Cog.listener("on_message_without_command")
    async def _on_message(self, message):
        data = await self.config.member(message.author)
