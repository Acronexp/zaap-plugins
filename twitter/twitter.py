import logging

import discord
import requests
from redbot.core import commands, Config, checks

logger = logging.getLogger("red.zaap-plugins.twitter")

class Twitter(commands.Cog):
    """Utilisation de Twitter à travers le bot"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        default_guild = {"IFTTT_EVENT": None,
                         "IFTTT_MAKER_KEY": None}
        self.config.register_guild(**default_guild)

    async def post_tweet(self, guild: discord.Guild, message: str):
        tweet = {}
        tweet["value1"] = message
        event, key = await self.config.guild(guild).IFTTT_EVENT(), await self.config.guild(guild).IFTTT_MAKER_KEY()
        requests.post(f"https://maker.ifttt.com/trigger/{event}/with/key/{key}", data=tweet)

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def tweet(self, ctx, *message):
        """Envoyer un tweet sur le compte configuré

        Il peut y avoir un certain temps entre la commande et l'apparition du tweet sur le compte"""
        message = " ".join(message)
        if await self.config.guild(ctx.guild).IFTTT_EVENT() and await self.config.guild(ctx.guild).IFTTT_MAKER_KEY():
            if len(message) <= 280:
                try:
                    await self.post_tweet(ctx.guild, message)
                    await ctx.send("**Envoyé** • Le message a été tweeté.\n"
                                   "Il peut se passer plusieurs minutes avant l'apparition du tweet.")
                except Exception as e:
                    logger.error(e, exc_info=True)
                    await ctx.send("**Erreur** • Le tweet n'a pas été envoyé. Vérifiez le nom de l'évènement IFTTT et "
                                   "votre clef Event Maker.")
            else:
                await ctx.send("**Trop long** • Le message ne peut faire plus de 280 caractères.")
        else:
            await ctx.send("**Non configuré** • Utilisez `;twitterset` pour configurer le nom de l'event IFTTT et "
                           "votre clef secrète Event Maker (options IFTTT).")

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def twitterset(self, ctx, event_name: str = None, maker_key: str = None):
        """Configurer la liaison Bot <-> IFTTT <-> Twitter"""
        if event_name:
            await self.config.guild(ctx.guild).IFTTT_EVENT.set(event_name)
            await ctx.send("**Nom d'évènement** • Modifié")
        else:
            await self.config.guild(ctx.guild).IFTTT_EVENT.set(None)
            await ctx.send("**Nom d'évènement** • Effacé")
        if maker_key:
            await self.config.guild(ctx.guild).IFTTT_MAKER_KEY.set(maker_key)
            await ctx.send("**Clef Maker** • Modifié")
        else:
            await self.config.guild(ctx.guild).IFTTT_MAKER_KEY.set(None)
            await ctx.send("**Clef Maker** • Effacé")

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def tweettest(self, ctx):
        """Teste les identifiants donnés"""
        if await self.config.guild(ctx.guild).IFTTT_EVENT() and await self.config.guild(ctx.guild).IFTTT_MAKER_KEY():
            try:
                await self.post_tweet(ctx.guild, "Test : ✅ Connexion établie avec Zaap")
                await ctx.send("**Envoyé** • Message de test envoyé.\n"
                               "Il peut se passer plusieurs minutes avant l'apparition du tweet.")
            except Exception as e:
                logger.error(e, exc_info=True)
                await ctx.send("**Erreur** • Le tweet n'a pas été envoyé. Vérifiez le nom de l'évènement IFTTT et "
                               "votre clef Event Maker.")
        else:
            await ctx.send("**Non configuré** • Utilisez `;twitterset` pour configurer le nom de l'event IFTTT et "
                           "votre clef secrète Event Maker (options IFTTT).")




