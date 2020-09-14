import logging
import random
import time

import discord
from redbot.core import Config, checks, commands

logger = logging.getLogger("red.zaap-plugins.quit")

DEFAULT_LISTS = {
    "default_french": [
        "{user.name} a quitté {guild.name}.",
        "{user.name} n'est plus joignable.",
        "Le serveur a perdu {user.name}.",
        "Au revoir, {user.name} !",
        "A la prochaine, {user.name} !",
        "Ce n'est qu'un au revoir, {user.name} !",
        "A jamais {user.name} !",
        "{user.name} est parti ouvrir son propre serveur...",
        "{user.name} s'envole vers d'autres cieux !",
        "{user.name} s'est trompé de bouton.",
        "Bye {user.name} !",
        "C'est la fin pour {user.name}.",
        "{user.name} a ragequit {guild.name}.",
        "A plus dans le bus, {user.name} !",
        "On m'annonce que {user.name} a décidé de prendre ses valises et quitter le serveur.",
        "Plus besoin de bloquer {user.name}, il est parti !",
        "{user.name} a pris sa retraite.",
        "{user.name} a pris congé.",
        "{user.name} est parti voir ailleurs.",
        "{user.name} n'est plus sur la liste."],
    "default_english": [
        "Bye {user.name} !",
        "Goodbye, {user.name} !",
        "The server lost {user.name}...",
        "See you soon, {user.name}.",
        "Farewell, {user.name}...",
        "{user.name} decided to go open his own server.",
        "{user.name} missed a button.",
        "{user.name}, see you later, alligator.",
        "You no longer need to block {user.name}, he left !",
        "{user.name} has taken his retirement.",
        "{user.name} took leave.",
        "{user.name} went to look elsewhere."],
    "plus_french": [ # Avec plein de refs.
        "{user.name} est tombé d'un trottoir.",
        "{user.name} est parti se cacher sur d'autres serveurs...",
        "{user.name} n'avait pas de masque.",
        "{user.name} est parti s'entrainer pour devenir le meilleur dresseur.",
        "{user.name} est parti dans les montagnes s'entrainer pour maîtriser l'armure du Dragon.",
        "{user.name} n'est plus là.",
        "{user.name} est parti prendre l'air.",
        "{user.name} s'est téléporté ailleurs.",
        "{user.name} est sorti de cette prison qu'est l'appartenance à ce serveur.",
        "{user.name} est désormais de l'autre côté du miroir.",
        "{user.name} est parti chercher les 7 boules de cristal.",
        "{user.name} a fait une overdose de chloroquine...",
        "Adieu, {user.name}. Tu ne nous manquera pas.",
        "{user.name}, tu hors de ma vue.",
        "{user.name} a rejoint la fosse aux randoms."
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
                         "custom_list": [],
                         "toggle_temps": False}
        self.config.register_guild(**default_guild)
        self.temps = {}

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
    async def chrono(self, ctx):
        """Activer/désactiver l'ajout du chrono de connexion lorsqu'il est court (quelqu'un qui vient et repart aussitôt"""
        if await self.config.guild(ctx.guild).channel():
            if await self.config.guild(ctx.guild).toggle_temps():
                await self.config.guild(ctx.guild).toggle_temps.set(False)
                await ctx.send(f"**Désactivé** • Le chrono ne s'affichera plus.")
            else:
                await self.config.guild(ctx.guild).toggle_temps.set(True)
                await ctx.send(f"**Activé** • Le temps chrono s'affichera si un membre a quitté le serveur dans un temps court après son arrivée.")
        else:
            await ctx.send(
                f"**Impossible** • Activez d'abord les messages d'arrivée avec `;quitmsg toggle` avant de modifier les listes utilisées.")

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
        `red` = Rouge de la palette utilisée par Discord"""
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

    def seconds_format(self, seconds: int):
        m = s = 0
        while seconds >= 60:
            m += 1
            seconds -= 60
        s = round(seconds, 2)
        all = []
        if m: all.append(str(m) + "m")
        if s: all.append(str(s) + "s")
        txt = " ".join(all)
        return txt

    @commands.Cog.listener()
    async def on_member_join(self, user):
        guild = user.guild
        if await self.config.guild(guild).channel():
            self.temps[user.id] = time.time()

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
                if await self.config.guild(guild).toggle_temps():
                    if user.id in self.temps:
                        chrono = time.time() - self.temps[user.id]
                        if chrono <= 300:
                            chrono = self.seconds_format(chrono)
                            em.set_footer(text=f"⏱️ {chrono}")
                if await self.config.guild(guild).delete_delay() > 0:
                    await channel.send(embed=em, delete_after= await self.config.guild(guild).delete_delay())
                else:
                    await channel.send(embed=em)
            else:
                if await self.config.guild(guild).delete_delay() > 0:
                    await channel.send(final, delete_after= await self.config.guild(guild).delete_delay())
                else:
                    await channel.send(final)