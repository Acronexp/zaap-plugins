import logging

import discord
from redbot.core import Config, checks, commands

logger = logging.getLogger("red.zaap-plugins.xrole")

_RULES = {
    "simple": "Rôle attribué à l'arrivée du membre, sans aucune vérification supplémentaire (CA)",
    "free": "Rôle auto-géré librement par les membres (CN)",
    "request": "Rôle auto-géré par les membres après confirmation par un modérateur (CN)",
    "captcha": "Rôle attribué après résolution d'un Captcha (CA)",
    "min.created": "Rôle attribué une fois l'âge min. du compte (en jours) atteint (CA)",
    "max.created": "Rôle retiré une fois l'âge max. du compte (en jours) atteint (CP)",
    "min.joined": "Rôle attribué une fois le nb. de jours min. sur ce serveur atteint (CA)",
    "max.joined": "Rôle retiré une fois le nb. de jours max. sur ce serveur atteint (CP)",
    "min.messages": "Rôle attribué une fois le nb. de messages min. postés depuis l'arrivée (CA)",
    "max.messages": "Rôle retiré une fois le nb. de messages max. postés depuis l'arrivée (CP)",
}

class XRole(commands.Cog):
    """Gestionnaire automatique de rôles"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)

        default_guild = {}
        self.config.register_guild(**default_guild)

    @commands.group(name="xrole")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_messages=True)
    async def _xrole(self, ctx):
        """Gestion des messages de départ"""

    @_xrole.command()
    async def help(self, ctx):
        """Pages d'aide pour comprendre le fonctionnement de XRole"""
        color = await self.bot.get_embed_color(ctx.channel)
        em = discord.Embed(title="Aide **XRole**", color=color,
                           description="__Note :__ les règles jouant sur l'attribution d'un rôle ne sont *jamais rétroactives* (voir terminologie)")
        addtxt = "**Syntaxe :** `xrole new <role> [regles]`\n\n" \
                 "Les règles s'écrivent sous la forme suivante : `nom=valeur`\n" \
                 "Il ne doit pas y avoir d'espace dans une règle, les espaces séparent chaque règle s'il y en a plusieurs. " \
                 "Les règles ne contenant pas `min/max` ne demandentpas de valeur et s'ajoutent simplement par le nom. " \
                 "Certaines règles sont incompatibles entre-elles.\n" \
                 "__Exemple :__ `xrole new @Role min.joined=7 min.messages=100` fera en sorte que le rôle *@Role* soit attribué " \
                 "automatiquement lorsqu'un membre a rejoint depuis += 7 jours et a écrit += 100 messages."
        em.add_field(name="Ajouter un rôle", value=addtxt, inline=False)

        deltxt = "**Syntaxe :** `xrole remove <role>`\n\n" \
                 "Ceci supprimera seulement les règles liées au rôle, mais ne supprimera pas le rôle lui-même."
        em.add_field(name="Retirer un rôle", value=deltxt, inline=False)

        edittxt = "**Syntaxe :** `xrole edit <role> [regles]`\n\n" \
                 "Les nouvelles règles remplaceront les anciennes."
        em.add_field(name="Editer un rôle", value=edittxt, inline=False)

        showtxt = "**Syntaxe :** `xrole show <role>`"
        em.add_field(name="Afficher les règles d'un rôle", value=showtxt, inline=False)
        em.set_footer(text="Page n°1 • Utiliser les règles de rôles")
        await ctx.send(embed=em)

        liste = ""
        for k in _RULES:
            liste += f"`{k}` ∙ *{_RULES[k]}*\n"
        em = discord.Embed(title="Aide **XRole**", description=liste, color=color)
        desc = "- **Condition d'attribution (CA)** = Condition qui joue lorsque le rôle doit être donné au membre [non rétroactif]\n" \
               "- **Condition de perte (CP)** = Condition qui joue lorsqu'un rôle doit être retiré [rétroactif]\n" \
               "- **Condition neutre (CN)** = Condition dépendante d'une action extérieure"
        em.add_field(name="Terminologie", value=desc)
        em.set_footer(text="Page n°2 • Liste des règles applicables")
        await ctx.send(embed=em)

    @_xrole.command()
    async def new(self, ctx, role: discord.Role, *rules):
        """Ajoute un rôle à autogérer et définir des conditions d'obtention"""


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild:
            user = message.author
