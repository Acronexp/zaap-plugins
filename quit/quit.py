import logging
from random import random

import discord
from redbot.core import Config, checks, commands

logger = logging.getLogger("red.zaap-plugins.quit")

DEFAULT_LISTS = {
    "default_french": [
        "{user.mention} a quitté {guild.name}.",
        "{user.mention} n'est plus joignable.",
        "Le serveur a perdu {user.mention}.",
        "Au revoir, {user.mention} !",
        "A la prochaine, {user.mention} !",
        "Ce n'est qu'un au revoir, {user.mention} !",
        "A jamais {user.mention} !",
        "{user.mention} est parti ouvrir son propre serveur...",
        "{user.mention} s'envole vers d'autres cieux !",
        "{user.mention} s'est trompé de bouton.",
        "Bye {user.mention} !",
        "C'est la fin pour {user.mention}.",
        "{user.mention} a ragequit {guild.name}.",
        "A plus dans le bus, {user.mention} !",
        "On m'annonce que {user.mention} a décidé de prendre ses valises et quitter le serveur.",
        "Plus besoin de bloquer {user.mention}, il est parti !",
        "{user.mention} a pris sa retraite.",
        "{user.mention} a pris congé.",
        "{user.mention} est parti voir ailleurs."],
    "default_english": [
        "Bye {user.mention} !",
        "Goodbye, {user.mention} !",
        "The server lost {user.mention}...",
        "See you soon, {user.mention}.",
        "Farewell, {user.mention}...",
        "{user.mention} decided to go open his own server.",
        "{user.mention} missed a button.",
        "{user.mention}, see you later, alligator.",
        "You no longer need to block {user.mention}, he left !",
        "{user.mention} has taken his retirement.",
        "{user.mention} took leave.",
        "{user.mention} went to look elsewhere."],
    "plus_french": [ # Avec plein de refs.
        "{user.mention} est tombé d'un trottoir.",
        "{user.mention} est parti se cacher sur d'autres serveurs...",
        "{user.mention} n'avait pas de masque.",
        "{user.mention} est parti s'entrainer pour devenir le meilleur dresseur.",
        "{user.mention} est parti dans les montagnes s'entrainer pour maitriser l'armure de bronze du Dragon.",
        "{user.mention} n'est plus là.",
        "{user.mention} est parti prendre l'air.",
        "{user.mention} s'est téléporté ailleurs.",
        "{user.mention} est sorti de cette prison qu'est l'appartenance à ce serveur.",
        "{user.mention} est désormais de l'autre côté du miroir.",
        "{user.mention} est parti chercher les 7 boules de cristal.",
        "{user.mention} a fait une overdose de chloroquine..."
    ]
}

class Quit(commands.Cog):
    """Gestionnaire de messages de départ"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)

        default_guild = {"channel": None,
                         "use_embed": True,
                         "embed_color": "user",
                         "meta_deco": "📣 {}",
                         "used": ["default_french"],
                         "delete_delay": 0,
                         "custom_list": []}
        self.config.register_guild(**default_guild)

    @commands.group(name="quitmsg")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_messages=True)
    async def _quitmsg(self, ctx):
        """Gestion des messages de départ"""

    @_quitmsg.command()
    async def toggle(self, ctx, channel: discord.TextChannel = None):
        """Activer/désactiver les messages de départ sur un salon écrit"""
        if not await self.config.guild(ctx.guild).channel():
            if channel:
                await self.config.guild(ctx.guild).channel.set(channel.id)
                await ctx.send(f"**Succès** • Salon {channel.mention} réglé pour recevoir les messages de départ.")
            else:
                await ctx.send(f"**Impossible** • Fournissez un salon sur lequel les messages doivent apparaître.")
        else:
            await self.config.guild(ctx.guild).channel.set(None)
            await ctx.send(f"**Succès** • Plus aucun salon n'affichera les messages de départ.")

    @_quitmsg.command()
    async def embed(self, ctx):
        """Activer/désactiver l'affichage en 'Embed' des messages de départ"""
        if await self.config.guild(ctx.guild).use_embed():
            await self.config.guild(ctx.guild).use_embed.set(False)
            await ctx.send(f"**Désactivé** • Les messages de départ s'afficheront au format classique.")
        else:
            await self.config.guild(ctx.guild).use_embed.set(True)
            await ctx.send(f"**Activé** • Les messages de départ s'afficheront au format Embed.")

    @_quitmsg.command()
    async def color(self, ctx, type: str):
        """Change la façon dont le bot choisi la couleur d'affichage (seulement en format Embed)

        __Types :__
        `user` = Prend la couleur du membre qui vient de quitter (par défaut)
        `core` = Prend la couleur des embeds par défaut du bot défini dans les options de coeur
        `bot` = Prend la couleur du bot sur le serveur
        'red` = Rouge de la palette utilisée par Discord"""
        if await self.config.guild(ctx.guild).use_embed():
            if type.lower() in ["user", "core", "bot", "red"]:
                await self.config.guild(ctx.guild).embed_color.set(type)
                await ctx.send(f"**Changement réalisé** • Le bot utilisera le type `{type}` pour déterminer la couleur de l'Embed.")
            else:
                await ctx.send(f"**Type invalide** • Consultez `;help quitmsg color` pour voir les types valides.")
        else:
            await ctx.send(f"**Impossible** • Activez d'abord l'affichage en Embed avec `;quitmsg embed` avant de modifier ce paramètre.")

    @_quitmsg.command()
    async def deco(self, ctx, *deco):
        """Modifie le décorateur des messages de départ (ce qui \"englobe\" les messages)

        Le message s'insère dans l'espace entre les crochets (`{}`). Pour retirer cette décoration, laissez le champ [deco] vide.
        __Exemples__:
        `📣 {}` (par défaut)
        `Départ : {}`
        `>>> *{}*`
        `***{}***`"""
        if deco:
            deco = " ".join(deco)
            await self.config.guild(ctx.guild).meta_deco.set(deco)
            await ctx.send(f"**Changement réalisé** • La décoration de message de départ a été modifiée avec succès.")
        else:
            await self.config.guild(ctx.guild).meta_deco.set("{}")
            await ctx.send(f"**Changement réalisé** • La décoration de message de départ a été retirée avec succès.")

    @_quitmsg.command()
    async def delay(self, ctx, delai: int):
        """Modifie le délai de suppression du message de départ

        Pour ne pas supprimer le message (par défaut), mettre 0"""
        if delai >= 0:
            await self.config.guild(ctx.guild).delete_delay.set(int(delai))
            if delai > 0:
                await ctx.send(f"**Changement réalisé** • Le message de départ sera supprimé après {delai} secondes.")
            else:
                await ctx.send(f"**Changement réalisé** • Le message de départ ne sera pas supprimé.")
        else:
            await ctx.send(f"**Erreur** • Le délai doit être positif (ou nul si vous voulez désactiver la suppression).")

    @_quitmsg.command()
    async def lists(self, ctx, *noms):
        """Modifie les listes utilisées pour sélectionner un message de départ lors du départ d'un membre

        Pour voir les listes disponibles, faîtes la commande sans remplir le champ [noms]"""
        if await self.config.guild(ctx.guild).channel():
            if noms:
                for n in noms:
                    if n.lower() not in DEFAULT_LISTS: # Pour l'instant il n'y a que les listes par défaut, à changer plus tard (TODO)
                        await ctx.send(
                            f"**Erreur** • La liste {n} n'existe pas. Faîtes `;quitmsg lists` pour voir les listes disponibles.")
                        return
                await self.config.guild(ctx.guild).used.set([i.lower() for i in noms])
                await ctx.send(
                    "**Changement réalisé** • Les listes suivantes seront désormais utilisées: {}".format(", ".join(noms)))
            else:
                txt = "**Listes disponibles**: {}".format(", ".join([n for n in DEFAULT_LISTS]))
                await ctx.send(txt)
        else:
            await ctx.send(
                f"**Impossible** • Activez d'abord les messages d'arrivée avec `;quitmsg toggle` avant de modifier les listes utilisées.")

    @commands.Cog.listener()
    async def on_member_remove(self, user):
        guild = user.guild
        if await self.config.guild(guild).channel():
            channel = self.bot.get_channel(await self.config.guild(guild).channel())
            lists = [i for sub in [DEFAULT_LISTS[l] for l in await self.config.guild(guild).used()] for i in sub]
            msg = random.choice(lists)
            formated = msg.format(user=user, guild=user.guild, bot=self.bot.user)
            deco = await self.config.guild(guild).meta_deco()
            final = deco.format(formated)
            if await self.config.guild(guild).use_embed():
                color_type = await self.config.guild(guild).embed_color()
                if color_type == "user":
                    color = user.color
                elif color_type == "bot":
                    color = self.bot.user.color
                elif color_type == "core":
                    color = await self.bot.get_embed_color(channel)
                else:
                    color = 0xf04747

                em = discord.Embed(description=final, color=color)
                if await self.config.guild(guild).delete_delay() > 0:
                    await channel.send(embed=em, delete_after= await self.config.guild(guild).delete_delay())
                else:
                    await channel.send(embed=em)
            else:
                if await self.config.guild(guild).delete_delay() > 0:
                    await channel.send(final, delete_after= await self.config.guild(guild).delete_delay())
                else:
                    await channel.send(final)