import logging
from datetime import datetime, timedelta

import discord
from redbot.core import Config, checks, commands

logger = logging.getLogger("red.zaap-plugins.bday")

class Bday(commands.Cog):
    """Gestionnaire de messages de départ"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)

        default_user = {"date": None,
                        "year": None}
        default_guild = {"role": None,
                         "send_msg": False,
                         "msg": "Bon anniversaire **{user.name}** !\n─ Les membres de {guild.name}"}
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)
        self.last_day = None

    @commands.command()
    async def bday(self, ctx, date: str):
        """Donne au bot votre date de naissance (JJ/MM)

        Mettre ? à la place de la date vous donnera la date que vous avez rentré dans le bot (s'il y en a une)
        Cette valeur est valable dans tous les serveurs où se trouve le bot"""
        author = ctx.author
        if date != "?":
            if len(date) == 5 and "/" in date:
                await self.config.user(author).date.set(date)
                await ctx.send("**Date ajoutée** • Vous recevrez un rôle dédié le jour de votre anniversaire sur les serveurs ayant activé l'option.")
            else:
                await ctx.send(
                    "**Erreur** • La date doit être rentrée au format JJ/MM. Si vous voulez retirer votre date de naissance, utilisez `;forgetbday`.")
        elif await self.config.user(author).date():
            if await self.config.user(author).year() == datetime.now().strftime("%Y"):
                await ctx.send(
                    "**Info** • Vous avez déjà indiqué être né un **{}**. Je l'ai déjà été fêté avec vous cette année.".format(await self.config.user(author).date()))
            else:
                await ctx.send(
                    "**Info** • Vous avez déjà indiqué être né un **{}**. Je ne l'ai pas (encore) fêté avec vous cette année.".format(
                        await self.config.user(author).date()))
        else:
            await ctx.send(
                "**Info** • Vous n'avez pas encore indiqué de date d'anniversaire.")

    @commands.command()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_messages=True)
    async def userbday(self, ctx, user: discord.User, date: str):
        """Donne la date de naissance d'un membre (JJ/MM)"""
        author = user
        if len(date) == 5 and "/" in date:
            await self.config.user(author).date.set(date)
            await ctx.send(
                "**Date ajoutée** • La date d'anniversaire du membre a été réglée.")
        else:
            await ctx.send(
                "**Erreur** • La date d'anniversaire doit être au format JJ/MM.")

    @commands.command()
    async def forgetbday(self, ctx):
        """Efface votre date de naissance des données du bot (sur tous les serveurs)"""
        author = ctx.author
        if await self.config.user(author).date():
            await self.config.user(author).date.set(None)
            await self.config.user(author).year.set(None)
            await ctx.send(
                "**Date retirée** • Votre anniversaire ne sera plus souhaité par les serveurs ayant activé l'option.")
        else:
            await ctx.send(
                "**Erreur** • Votre date d'anniversaire ne figure pas dans mes données.")

    @commands.group(name="modbday")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_messages=True)
    async def _modbday(self, ctx):
        """Gestion du rôle & message d'anniversaire automatique"""

    @_modbday.command()
    async def role(self, ctx, role: discord.Role = None):
        """Active/désactive l'attribution auto. d'un rôle à l'anniversaire d'un membre

        Laisser le champ [role] vide permet de désactiver l'attribution automatique d'un rôle d'anniversaire"""
        guild = ctx.guild
        if role:
            await self.config.guild(guild).role.set(role.id)
            await ctx.send(
                f"**Rôle ajouté & fonctionnalité activée** • Les membres recevront le rôle {role.name} à leur anniversaire (s'il l'ont réglé avec `;bday`).")
        else:
            await self.config.guild(guild).role.set(None)
            await ctx.send(
                "**Rôle retiré & fonctionnalité désactivée** • Les membres ne recevront plus de rôle à leur anniversaire.")

    @_modbday.command()
    async def message(self, ctx, *msg):
        """Modifie le message auto. envoyé à l'anniversaire d'un membre dans ses MP

        Laissez vide pour remettre le message par défaut (ci-dessous)
        `Bon anniversaire **{user.name}** !\n─ Les membres de {server.name}`"""
        guild = ctx.guild
        if msg:
            msg = " ".join(msg)
            await self.config.guild(guild).msg.set(msg)
            await ctx.send(
                f"**Message modifié** • Les membres recevront ce message à leur anniversaire (s'il l'ont réglé avec `;bday`).")
        else:
            await self.config.guild(guild).msg.set("Bon anniversaire **{user.name}** !\n─ Les membres de {server.name}")
            await ctx.send(
                "**Message remis par défaut** • Le message sera le suivant : `Bon anniversaire **{user.name}** !\n─ Les membres de {server.name}`")

    @_modbday.command()
    async def togglemsg(self, ctx):
        """Active/désactive l'envoi d'un message auto. à l'anniversaire d'un membre du serveur

        Modifiez le message en question avec `;modbday message`"""
        guild = ctx.guild
        if await self.config.guild(guild).send_msg():
            await self.config.guild(guild).send_msg.set(False)
            await ctx.send(
                "**Option désactivée** • Les membres fêtant leur anniversaire ne recevront pas de message de ce serveur en MP.")
        else:
            await self.config.guild(guild).send_msg.set(True)
            await ctx.send(
                "**Option activée** • Les membres du serveur recevront un message auto. à leur anniversaire (par MP). Voir `;help modbday message`.")

    @commands.command()
    @checks.is_owner()
    async def bdaycheck(self, ctx):
        """Reset le cache et performe de nouveau un check des anniversaire de la journée (pour ceux pour lesquels il n'a pas été encore fêté)"""
        self.last_day = None
        await ctx.send("**Reset effectué** • Les membres n'ayant rien reçu aujourd'hui devraient pouvoir le recevoir désormais.")

    @commands.Cog.listener() # J'utilise ça pour éviter d'avoir à utiliser une boucle alors qu'on a besoin que d'UN check par jour, pas 3000
    async def on_message(self, message):
        now = datetime.now()
        hier = now - timedelta(days=1)
        if now.date() != self.last_day:
            self.last_day = now.date()
            users = await self.config.all_users()
            guilds = await self.config.all_guilds()
            for user in users:
                u = self.bot.get_user(user)
                if users[user]["date"] == now.strftime("%d/%m"):
                    if users[user]["year"] != now.strftime("%Y"): # Vérifier qu'on a pas déjà fêté son anniv cette année, en cas de redémarrage etc.
                        send = False
                        await self.config.user(u).year.set(now.strftime("%Y"))
                        em = discord.Embed(title="Bon anniversaire !")
                        for guild in guilds:
                            g = self.bot.get_guild(guild)
                            if guilds[guild]["send_msg"]:
                                send = True
                                em.add_field(name=f"Message de {g.name}", value=guilds[guild]["msg"].format(user=u, guild=g, server=g))
                            if guilds[guild]["role"]:
                                try:
                                    member = g.get_member(user)
                                    role = g.get_role(guilds[guild]["role"])
                                    await member.add_roles(role, reason="Anniversaire aujourd'hui")
                                except:
                                    logger.error("Impossible de donner le rôle ID:{} à {}".format(guilds[guild]["role"], u.name), exc_info=True)
                        if send:
                            try:
                                await u.send(embed=em)
                            except:
                                pass
                elif users[user]["date"] == hier.strftime("%d/%m"):
                    for guild in guilds:
                        if guilds[guild]["role"]:
                            g = self.bot.get_guild(guild)
                            try:
                                member = g.get_member(user)
                                role = g.get_role(guilds[guild]["role"])
                                if role in g.roles:
                                        await member.remove_roles(role, reason="Fin de l'anniversaire")
                            except:
                                logger.error(
                                    "Impossible de retirer le rôle ID:{} à {}".format(guilds[guild]["role"], u.name),
                                    exc_info=True)

            logger.info("Vérification d'anniversaire réalisée pour {}".format(now.strftime("%d/%m/%Y")))


