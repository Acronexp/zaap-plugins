import logging
import time
from datetime import datetime

import discord
import requests
from redbot.core import Config, commands, checks
from tabulate import tabulate

logger = logging.getLogger("red.zaap-plugins.logs")

_TRIGGERS = {
    "message.delete" : "Message supprimé",
    "message.edit": "Message édité",
    "voice.join": "Connexion vocale",
    "voice.quit": "Déconnexion vocale",
    "voice.update": "Changement de salon vocal",
    "voice.mute": "Membre mute/demute serveur",
    "voice.selfmute": "Membre self-mute/demute ",
    "voice.deaf": "Membre ajouté/retiré de sourdine",
    "voice.selfdeaf": "Membre sourd/non-sourd perso.",
    "voice.stream": "Début/fin de stream",
    "voice.video": "Début/fin de diffusion de vidéo",
    "member.join": "Nouvel arrivant",
    "member.join.infos": "Infos du nouvel arrivant",
    "member.quit": "Départ du serveur",
    "member.ban": "Membre banni",
    "member.unban": "Membre débanni",
    "member.update.name": "Changement de pseudo",
    "member.update.nick": "Changement de surnom",
    "member.update.avatar": "Changement d'avatar",
    "invite.create": "Création d'invitation",
    "invite.delete": "Suppression d'une invitation",
    "discord.status": "Instabilité des serveurs Discord",
    "discord.guilds.offline": "Déconnexions de serveurs"
}

class LogsError(Exception):
    pass

class CouldNotSend(LogsError):
    pass

class ChannelError(LogsError):
    pass

class Logs(commands.Cog):
    """Module de logging des évènements discord (& des utilisations de commandes)"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        default_guild = {"channels": {},
                         "colors": {}}
        self.config.register_guild(**default_guild)
        self.channels = {}
        self.delays = {"discord_status": 0, "guilds_disconnect": 0}
        try:
            self.social = self.bot.get_cog("Social")
        except:
            self.social = None
            logger.info("Impossible de charger Social.py, les infos de membres ne seront pas disponibles")

    async def preload_channels(self, guild: discord.Guild):
        """Charge d'avance les salons pour fluidifier l'envoi des logs"""
        loadcache = {}
        all_channels = guild.text_channels
        triggers = await self.config.guild(guild).channels()
        for trig in triggers:
            loadcache[trig] = [chan for chan in all_channels if chan.id in triggers[trig]]
        self.channels[guild.id] = loadcache
        return self.channels[guild.id]

    async def get_preloaded_channels(self, guild: discord.Guild):
        if guild.id not in self.channels:
            return await self.preload_channels(guild)
        return self.channels[guild.id]

    async def manage_logging(self, guild: discord.Guild, trigger: str, content: discord.Embed):
        """Gère l'envoi des logs sur les channels liés du serveur"""
        triggers = await self.get_preloaded_channels(guild)
        if trigger.lower() in triggers:
            channels = triggers[trigger.lower()]
            colors = await self.config.guild(guild).colors()
            for chan in channels:
                try:
                    if colors.get(trigger.lower(), False):
                        content.colour = colors[trigger.lower()]
                    else:
                        content.colour = await self.bot.get_embed_color(chan)
                    await chan.send(embed=content)
                    return True
                except:
                    raise CouldNotSend(f"Un log du trigger {trigger} n'a pas pu être envoyé sur {chan.mention}")
        return None

    async def global_logging(self, trigger: str, content: discord.Embed):
        """Envoie sur tous les serveurs avec le trigger activé"""
        all_guilds = self.bot.guilds
        traceback = []
        for guild in all_guilds:
            preload = await self.get_preloaded_channels(guild)
            if preload.get(trigger.lower(), False):
                try:
                    result = await self.manage_logging(guild, trigger, content)
                    traceback.append((guild.id, result))
                except:
                    pass
        return traceback

    @commands.group(name="logs")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_messages=True)
    async def _logs(self, ctx):
        """Commandes de gestion du logging"""

    @_logs.command(name="color")
    async def embed_color(self, ctx, trigger: str, color: str = None):
        """Modifie la couleur de l'Embed d'un trigger

        Pour remettre la couleur du bot (par défaut) il suffit de ne pas rentrer de couleur"""
        trigger = trigger.lower()
        if trigger in _TRIGGERS:
            if color:
                try:
                    color = color.replace("#", "0x")
                    color = hex(int(color, 16))
                except:
                    await ctx.send("**Erreur** • La couleur doit être fournie au format hexadécimal (ex. `#D5D5D5` ou `0xD5D5D5`")
                em = discord.Embed(title="Couleur changée • Démonstration",
                                   description=f"La couleur du trigger `{trigger}` a été modifiée avec succès.",
                                   color=color)
            else:
                em = discord.Embed(title="Couleur retirée • Démonstration",
                                   description=f"La couleur du trigger `{trigger}` a été retirée.",
                                   color=await ctx.embed_color())

            perso = await self.config.guild(ctx.guild).colors()
            if color:
                perso[trigger] = color
            elif trigger in perso:
                del perso[trigger]
            await self.config.guild(ctx.guild).colors.set(perso)
            await ctx.send(embed=em)
        else:
            await ctx.send(f"**Erreur** • Ce nom de trigger n'existe pas. Consultez la liste avec `;logs list`.")

    @_logs.command(name="list")
    async def list_triggers(self, ctx):
        """Liste les nom de triggers acceptés"""

        em_color = await ctx.embed_color()
        tables = {}
        for t in _TRIGGERS:
            type = t.split(".")[0]
            if type not in tables:
                tables[type] = [t]
            else:
                tables[type].append(t)
        em = discord.Embed(color=em_color, description="Lister les triggers d'un salon : `;logs get`\n"
                                                       "Ajouter un trigger à ce salon : `;logs add`\n"
                                                       "Retirer un trigger à ce salon : `;logs remove`")
        em.set_footer(text="Utilisez \";help logs\" pour plus d'infos sur les commandes")
        em.set_author(name="Logs disponibles", icon_url=self.bot.user.avatar_url)
        for type in tables:
            title = f"Ciblant \"{type.title()}\""
            table = []
            for trig in tables[type]:
                table.append([trig, _TRIGGERS[trig]])
            em.add_field(name=title, value="```" + tabulate(table, headers=["Nom", "Déclencheur"]) + "```", inline=False)
        await ctx.send(embed=em)

    @_logs.command(name="add")
    async def add_logging(self, ctx, trigger: str, salon: discord.TextChannel = None):
        """Assigne un salon à un trigger de logs

        Si le paramètre [salon] n'est pas précisé, assignera le trigger au salon où est réalisée la commande"""

        guild = ctx.guild
        trigger = trigger.lower()
        if not salon:
            salon = ctx.channel
        if trigger in list(_TRIGGERS.keys()):
            channels = await self.config.guild(guild).channels()
            if trigger not in channels:
                channels[trigger] = [salon.id]
            elif salon.id not in channels[trigger]:
                channels[trigger].append(salon.id)
            else:
                return await ctx.send(f"**Inutile** • Le salon {salon.mention} est déjà lié à `{trigger}`")
            await self.config.guild(guild).channels.set(channels)
            await self.preload_channels(guild)
            await ctx.send(f"**Salon lié avec succès** • Le salon {salon.mention} "
                           f"affichera désormais les logs de type `{trigger}`")
        else:
            return await ctx.send(f"**Erreur** • Le trigger `{trigger}` n'existe pas. Consultez la liste avec `;logs list`")

    @_logs.command(name="remove")
    async def remove_logging(self, ctx, trigger: str, salon: discord.TextChannel = None):
        """Retire un trigger de logs à un salon

        Si le paramètre [salon] n'est pas précisé, le salon cible sera celui où vous réalisez la commande"""
        guild = ctx.guild
        trigger = trigger.lower()
        if not salon:
            salon = ctx.channel
        if trigger in list(_TRIGGERS.keys()):
            channels = await self.config.guild(guild).channels()
            if salon.id in channels[trigger]:
                channels[trigger].remove(salon.id)
                if not channels[trigger]:
                    del channels[trigger]
                await self.config.guild(guild).channels.set(channels)
                await self.preload_channels(guild)
                await ctx.send(f"**Trigger retiré avec succès** • Le salon {salon.mention} n'affichera plus les logs `{trigger}`")
            else:
                return await ctx.send(
                    f"**Erreur** • Le trigger `{trigger}` n'est pas lié à ce salon. Consultez la liste des triggers liés avec `;logs get {salon.mention}`")
        else:
            return await ctx.send(
                f"**Erreur** • Le trigger `{trigger}` n'existe pas. Consultez la liste avec `;logs list`")

    @_logs.command(name="get")
    async def get_triggers(self, ctx, salon: discord.TextChannel = None):
        """Affiche les triggers liés au salon cible"""
        em_color = await ctx.embed_color()
        guild = ctx.guild
        if not salon:
            salon = ctx.channel
        liste = []
        channels = await self.config.guild(guild).channels()
        for trig in channels:
            if salon.id in channels[trig]:
                liste.append([trig, _TRIGGERS[trig]])
        if liste:
            desc = "```" + tabulate(liste, headers=["Nom", "Déclencheur"]) + "```"
            em = discord.Embed(color=em_color, description=desc)
            em.set_author(name=f"Logs liés à #{salon.name}", icon_url=self.bot.user.avatar_url)
            await ctx.send(embed=em)
        else:
            return await ctx.send(
                f"Il n'y a aucun trigger de logs lié au salon {salon.mention}")


    @commands.Cog.listener()
    async def on_message(self, message):
        delay = self.delays["discord_status"]
        if delay + 300 < time.time():
            self.delays["discord_status"] = time.time()
            statuspage = requests.get("https://srhpyqt94yxb.statuspage.io/api/v2/status.json")
            status = statuspage.json()["status"]["indicator"]
            page = statuspage.json()["page"]["url"]
            ts = datetime.utcnow()
            if status != "none":
                em = discord.Embed(description=f"Les serveurs de Discord connaissent actuellement des instabilités. "
                                               f"Consultez {page} pour plus d'infos.", timestamp=ts)
                em.set_author(name="Instabilité des serveurs Discord", icon_url=self.bot.user.avatar_url)
                em.set_footer(text=f"Message global")
                await self.global_logging("discord.status", em)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild:
            if message.author:
                if message.author != self.bot.user:
                    preload = await self.get_preloaded_channels(message.guild)
                    ts = datetime.utcnow()
                    if preload.get("message.delete", False):
                        em = discord.Embed(description=message.content, timestamp=ts)
                        em.set_author(name=str(message.author) + " » Message supprimé", icon_url=message.author.avatar_url)
                        em.set_footer(text=f"{message.author.id} · #{message.channel.name}")
                        await self.manage_logging(message.guild, "message.delete", em)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.guild:
            if after.author:
                if after.author != self.bot.user:
                    if after.content != before.content:
                        preload = await self.get_preloaded_channels(after.guild)
                        if preload.get("message.edit", False):
                            em = discord.Embed(timestamp=after.created_at)
                            em.add_field(name="Avant", value=before.content)
                            em.add_field(name="Après", value=after.content)
                            em.set_author(name=str(after.author) + " » Message édité",
                                          icon_url=after.author.avatar_url, url=after.jump_url)
                            em.set_footer(text=f"{after.author.id} · #{after.channel.name}")
                            await self.manage_logging(after.guild, "message.edit", em)

    @commands.Cog.listener()
    async def on_voice_state_update(self, user, before, after):
        if user.guild:
            ts = datetime.utcnow()
            preload = await self.get_preloaded_channels(user.guild)

            if after.channel:
                if not before.channel:
                    if preload.get("voice.join", False):
                        em = discord.Embed(description=f"{user.mention} s'est connecté à {after.channel.mention}",
                                           timestamp=ts)
                        em.set_author(name=str(user) + " » Connexion à un salon vocal",
                                      icon_url=user.avatar_url)
                        em.set_footer(text=f"{user.id} · #{after.channel.name}")
                        await self.manage_logging(user.guild, "voice.join", em)
                elif after.channel != before.channel:
                    if preload.get("voice.update", False):
                        em = discord.Embed(description=f"{user.mention} est passé de {before.channel.mention} à {after.channel.mention}",
                                           timestamp=ts)
                        em.set_author(name=str(user) + " » Changement de salon",
                                      icon_url=user.avatar_url)
                        em.set_footer(text=f"{user.id} · #{before.channel.name} / #{after.channel.name}")
                        await self.manage_logging(user.guild, "voice.update", em)

            elif before.channel:
                if preload.get("voice.quit", False):
                    em = discord.Embed(description=f"{user.mention} s'est déconnecté de {before.channel.mention}",
                                       timestamp=ts)
                    em.set_author(name=str(user) + " » Déconnexion d'un salon vocal",
                                  icon_url=user.avatar_url)
                    em.set_footer(text=f"{user.id} · #{before.channel.name}")
                    await self.manage_logging(user.guild, "voice.quit", em)

            if before.channel and after.channel: # Déjà en vocal
                title = desc = type = None
                # Mute
                if before.mute > after.mute:
                    type = "voice.mute"
                    title = "Démute (serveur)"
                    desc = f"{user.mention} a été démute"
                elif before.mute < after.mute:
                    type = "voice.mute"
                    title = "Mute (serveur)"
                    desc = f"{user.mention} a été mute"

                # Self mute
                if before.self_mute > after.self_mute:
                    type = "voice.selfmute"
                    title = "Démute (personnel)"
                    desc = f"{user.mention} s'est démute"
                elif before.self_mute < after.self_mute:
                    type = "voice.selfmute"
                    title = "Mute (personnel)"
                    desc = f"{user.mention} s'est mute"

                # Deaf
                if before.deaf > after.deaf:
                    type = "voice.deaf"
                    title = "Sortie de sourdine (serveur)"
                    desc = f"{user.mention} a été retiré de la sourdine"
                elif before.deaf < after.deaf:
                    type = "voice.deaf"
                    title = "Sourdine (serveur)"
                    desc = f"{user.mention} a été mis en sourdine"

                # Self deaf
                if before.self_deaf > after.self_deaf:
                    type = "voice.selfdeaf"
                    title = "Sortie de sourdine (personnel)"
                    desc = f"{user.mention} s'est retiré de sourdine"
                elif before.self_deaf < after.self_deaf:
                    type = "voice.selfdeaf"
                    title = "Sourdine (personnel)"
                    desc = f"{user.mention} s'est mis en sourdine"

                # Stream
                if before.self_stream > after.self_stream:
                    type = "voice.stream"
                    title = "Fin de stream"
                    desc = f"{user.mention} a arrêté de streamer"
                elif before.self_stream < after.self_stream:
                    type = "voice.stream"
                    title = "Début de stream"
                    desc = f"{user.mention} a commencé à streamer sur {after.channel.mention}"

                # Video
                if before.self_video > after.self_video:
                    type = "voice.video"
                    title = "Fin de la vidéo"
                    desc = f"{user.mention} a arrêté de diffuser"
                elif before.self_video < after.self_video:
                    type = "voice.video"
                    title = "Début de diffusion de vidéo"
                    desc = f"{user.mention} a commencé à diffuser sur {after.channel.mention}"

                if all([title, desc, type]):
                    if preload.get(type, False):
                        em = discord.Embed(description=desc, timestamp=ts)
                        em.set_author(name=str(user) + f" » {title}", icon_url=user.avatar_url)
                        em.set_footer(text=f"{user.id} · #{after.channel.name}")
                        await self.manage_logging(user.guild, type, em)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if isinstance(after, discord.Member):
            if after.display_name != before.display_name:
                preload = await self.get_preloaded_channels(after.guild)
                if preload.get("member.update.nick", False):
                    ts = datetime.utcnow()
                    if after.display_name == after.name:
                        desc = f"{after.mention} a retiré son surnom (***{before.nick}***)"
                    else:
                        desc = f"{after.mention} a changé son surnom pour ***{after.nick}***"
                    em = discord.Embed(description=desc, timestamp=ts)
                    em.set_author(name=str(after) + " » Changement de surnom",
                                  icon_url=after.avatar_url)
                    em.set_footer(text=f"{after.id}")
                    await self.manage_logging(after.guild, "member.update.nick", em)

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        if isinstance(after, discord.Member):
            preload = await self.get_preloaded_channels(after.guild)
            if after.name != before.name:
                if preload.get("member.update.name", False):
                    ts = datetime.utcnow()
                    em = discord.Embed(description=f"*{before.name}* a changé son pseudo pour ***{after.name}***",
                                       timestamp=ts)
                    em.set_author(name=str(after) + " » Changement de pseudonyme",
                                  icon_url=after.avatar_url)
                    em.set_footer(text=f"{after.id}")
                    await self.manage_logging(after.guild, "member.update.name", em)
            if after.avatar_url != before.avatar_url:
                url = before.avatar_url.split("?")[0]
                if preload.get("member.update.avatar", False):
                    ts = datetime.utcnow()
                    em = discord.Embed(description=f"{after.mention} a changé d'avatar (affiché)",
                                       timestamp=ts)
                    em.set_author(name=str(after) + " » Changement d'avatar",
                                  icon_url=after.avatar_url)
                    em.set_thumbnail(url=url)
                    em.set_footer(text=f"{after.id}")
                    await self.manage_logging(after.guild, "member.update.avatar", em)

    @commands.Cog.listener()
    async def on_member_join(self, user):
        preload = await self.get_preloaded_channels(user.guild)
        ts = datetime.utcnow()
        if preload.get("member.join", False):
            em = discord.Embed(description=f"{user.mention} a rejoint le serveur", timestamp=ts)
            em.set_author(name=str(user) + " » Nouvel arrivant",
                          icon_url=user.avatar_url)
            em.set_footer(text=f"{user.id}")
            await self.manage_logging(user.guild, "member.join", em)

        if preload.get("member.join.infos", False) and self.social:
            created_since = (datetime.now() - user.created_at).days
            try:
                first_record = datetime.fromtimestamp(await self.social.config.guild(user.guild).records.get_raw(user.id))
            except:
                first_record = user.joined_at
            if first_record > user.joined_at:
                first_record = user.joined_at
            record_since = (datetime.now() - first_record).days

            desc = "**Ouverture du compte Discord** : {} · **{}**j\n" \
                   "**Première trace sur ce serveur** : {} · **{}**j".format(user.created_at.strftime("%d/%m/%Y"), created_since,
                                                                    first_record.strftime("%d/%m/%Y"), record_since)
            if await self.social.config.member(user).mod_notes():
                desc += f"\n__Notes de modération trouvées__ : utilisez `;uc {user.name}`"

            em = discord.Embed(description=desc, timestamp=ts)
            em.set_author(name=str(user) + " » Infos du nouvel arrivant",
                          icon_url=user.avatar_url)
            em.set_thumbnail(url=user.avatar_url)
            em.set_footer(text=f"{user.id}")
            await self.manage_logging(user.guild, "member.join.infos", em)

    @commands.Cog.listener()
    async def on_member_remove(self, user):
        preload = await self.get_preloaded_channels(user.guild)
        if preload.get("member.quit", False):
            ts = datetime.utcnow()
            em = discord.Embed(description=f"***{user.name}*** a quitté le serveur", timestamp=ts)
            em.set_author(name=str(user) + " » Départ du membre",
                          icon_url=user.avatar_url)
            em.set_footer(text=f"{user.id}")
            await self.manage_logging(user.guild, "member.quit", em)

    @commands.Cog.listener()
    async def on_member_ban(self, user):
        preload = await self.get_preloaded_channels(user.guild)
        if preload.get("member.ban", False):
            ts = datetime.utcnow()
            em = discord.Embed(description=f"***{user.name}*** a été banni du serveur", timestamp=ts)
            em.set_author(name=str(user) + " » Bannissement",
                          icon_url=user.avatar_url)
            em.set_footer(text=f"{user.id}")
            await self.manage_logging(user.guild, "member.ban", em)

    @commands.Cog.listener()
    async def on_member_unban(self, user):
        preload = await self.get_preloaded_channels(user.guild)
        if preload.get("member.unban", False):
            ts = datetime.utcnow()
            em = discord.Embed(description=f"***{user.name}*** a été débanni du serveur", timestamp=ts)
            em.set_author(name=str(user) + " » Débannissement",
                          icon_url=user.avatar_url)
            em.set_footer(text=f"{user.id}")
            await self.manage_logging(user.guild, "member.unban", em)

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        preload = await self.get_preloaded_channels(invite.guild)
        if preload.get("invite.create", False):
            ts = datetime.utcnow()
            em = discord.Embed(description=f"{invite.inviter.mention} a créé une invitation (**{invite.code}**)",
                               timestamp=ts)
            em.set_author(name="Création d'une invitation", icon_url=self.bot.user.avatar_url)
            em.set_footer(text=f"{invite.inviter.id}")
            await self.manage_logging(invite.guild, "invite.create", em)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        preload = await self.get_preloaded_channels(invite.guild)
        if preload.get("invite.delete", False):
            ts = datetime.utcnow()
            em = discord.Embed(description=f"L'invitation **{invite.code}** a été supprimée",
                               timestamp=ts)
            em.set_author(name="Suppression d'une invitation", icon_url=self.bot.user.avatar_url)
            em.set_footer(text=f"{invite.inviter.id}")
            await self.manage_logging(invite.guild, "invite.delete", em)

    @commands.Cog.listener()
    async def on_guild_unavailable(self, guild):
        delay = self.delays["guilds_disconnect"]
        if delay + 300 < time.time():
            self.delays["guilds_disconnect"] = time.time()
            ts = datetime.utcnow()
            em = discord.Embed(description=f"D'autres serveurs se sont déconnectés, "
                                           f"indiquant peut-être une instabilité de Discord.", timestamp=ts)
            em.set_author(name="Possible instabilité de Discord", icon_url=self.bot.user.avatar_url)
            em.set_footer(text=f"Message global")
            await self.global_logging("discord.guilds.offline", em)










