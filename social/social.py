import time
from datetime import datetime, timedelta
import discord

from redbot.core import Config, checks, commands

__version__ = "1.1.0"

ACTIVITY_TYPES = {
    discord.ActivityType.playing: "Joue",
    discord.ActivityType.watching: "Regarde",
    discord.ActivityType.listening: "Écoute",
    discord.ActivityType.streaming: "Diffuse"
}

STATUS_COLORS = {
    discord.Status.online: 0x40AC7B,
    discord.Status.idle: 0xFAA61A,
    discord.Status.dnd: 0xF04747,
    discord.Status.offline: 0x747F8D
}

class Social(commands.Cog):
    """Fonctionnalités sociales supplémentaires"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        default_member = {"names": [],
                          "nicknames": [],
                          "cons_days": [],
                          "logs": [],
                          "achievements": {}, # TODO: implémenter les succès
                          "mod_notes": {}}
        default_guild = {"achievements_alerts": True,
                         "records": {},
                         "secure_channel": None}

        self.config.register_member(**default_member)
        self.config.register_guild(**default_guild)

    def is_streaming(self, user: discord.Member):
        if user.activities:
            return any([activity.type is discord.ActivityType.streaming for activity in user.activities])
        return False

    def handle_custom(self, user):
        a = [c for c in user.activities if c.type == discord.ActivityType.custom]
        if not a:
            return None, discord.ActivityType.custom
        a = a[0]
        c_status = None
        if not a.name and not a.emoji:
            return None, discord.ActivityType.custom
        elif a.name and a.emoji:
            c_status = "{emoji} {name}".format(emoji=a.emoji, name=a.name)
        elif a.emoji:
            c_status = "{emoji}".format(emoji=a.emoji)
        elif a.name:
            c_status = "{name}".format(name=a.name)
        return c_status, discord.ActivityType.custom

    def handle_playing(self, user):
        p_acts = [c for c in user.activities if c.type == discord.ActivityType.playing]
        if not p_acts:
            return None, discord.ActivityType.playing
        p_act = p_acts[0]
        act = "Joue à {name}".format(name=p_act.name)
        return act, discord.ActivityType.playing

    def handle_streaming(self, user):
        s_acts = [c for c in user.activities if c.type == discord.ActivityType.streaming]
        if not s_acts:
            return None, discord.ActivityType.streaming
        s_act = s_acts[0]
        if isinstance(s_act, discord.Streaming):
            act = "Diffuse [{name}{sep}{game}]({url})".format(
                name=discord.utils.escape_markdown(s_act.name),
                sep=" | " if s_act.game else "",
                game=discord.utils.escape_markdown(s_act.game) if s_act.game else "",
                url=s_act.url,
            )
        else:
            act = ("Diffuse {name}").format(name=s_act.name)
        return act, discord.ActivityType.streaming

    def handle_listening(self, user):
        l_acts = [c for c in user.activities if c.type == discord.ActivityType.listening]
        if not l_acts:
            return None, discord.ActivityType.listening
        l_act = l_acts[0]
        if isinstance(l_act, discord.Spotify):
            act = "Écoute [{title}{sep}{artist}]({url})".format(
                title=discord.utils.escape_markdown(l_act.title),
                sep=" | " if l_act.artist else "",
                artist=discord.utils.escape_markdown(l_act.artist) if l_act.artist else "",
                url=f"https://open.spotify.com/track/{l_act.track_id}",
            )
        else:
            act = "Écoute {title}".format(title=l_act.name)
        return act, discord.ActivityType.listening

    def handle_watching(self, user):
        w_acts = [c for c in user.activities if c.type == discord.ActivityType.watching]
        if not w_acts:
            return None, discord.ActivityType.watching
        w_act = w_acts[0]
        act = "Regarde {name}".format(name=w_act.name)
        return act, discord.ActivityType.watching

    def get_status_string(self, user):
        string = ""
        for a in [
            self.handle_custom(user),
            self.handle_playing(user),
            self.handle_listening(user),
            self.handle_streaming(user),
            self.handle_watching(user),
        ]:
            status_string, status_type = a
            if status_string is None:
                continue
            string += f"> {status_string}\n"
        return string

    async def check_secure_channel(self, channel: discord.TextChannel):
        guild = channel.guild
        try:
            secure = await self.config.guild(guild).get_raw("secure_channel")
            if channel.id == secure:
                return True
        except KeyError:
            return False

    @commands.command(aliases=["uc"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def usercard(self, ctx, user: discord.Member = None):
        """Renvoie une carte de membre affichant diverses infos sur celui-ci

        [user] = si la carte affichée doit être celui du membre visé"""
        if not user: user = ctx.author
        guild = ctx.guild
        member = await self.config.member(user).all()

        created_since, joined_since = (datetime.now() - user.created_at).days, (datetime.now() - user.joined_at).days
        booster_since = (datetime.now() - user.premium_since).days if user.premium_since else False
        voice_channel = user.voice.channel.mention if user.voice else None

        embed_color = STATUS_COLORS[user.status] if not self.is_streaming(user) else 0x6438AA
        flames = len(member["cons_days"])
        if flames:
            last_msg = member["cons_days"][-1]
        else:
            last_msg = time.strftime("%d/%m/%Y", time.localtime())
        try:
            first_record = datetime.fromtimestamp(await self.config.guild(guild).records.get_raw(user.id))
        except KeyError:
            first_record = user.joined_at
        if first_record < user.joined_at:
            first_record = user.joined_at
        record_since = (datetime.now() - first_record).days
        logs = member["logs"][::-1]
        names, nicknames = member["names"][::-1], member["nicknames"][::-1]

        em = discord.Embed(title=str(user) if not user.nick else "{} « {} »".format(str(user), user.nick), description=self.get_status_string(user), color=embed_color)
        em.set_thumbnail(url=user.avatar_url)
        member_num = (sorted(guild.members, key=lambda m: m.joined_at or ctx.message.created_at).index(user) + 1)

        presence_txt = "**Création du compte**: {} · **{}**j\n" \
                       "**Arrivée sur le serveur**: {} · **{}**j\n" \
                       "**Première trace**: {} · **{}**j\n" \
                       "**Dernier message**: {} · \🔥{}".format(user.created_at.strftime("%d/%m/%Y"), created_since,
                                                                 user.joined_at.strftime("%d/%m/%Y"), joined_since,
                                                                 first_record.strftime("%d/%m/%Y"), record_since,
                                                                 last_msg, flames)
        if booster_since:
            presence_txt += "\n**Booste depuis**: {} · **{}**j".format(user.premium_since.strftime("%d/%m/%Y"),
                                                                        booster_since)
        em.add_field(name="Profil", value=presence_txt, inline=False)
        roles = user.roles[-1:0:-1]
        if roles:
            long, txt = 0, ""
            for r in roles:
                chunk = f"{r.mention} "
                if long + len(chunk) > 1018: # Pour les serveurs qui ont 300 rôles là, on vous voit
                    txt += "(...)"
                    break
                txt += chunk
                long += len(chunk)
            em.add_field(name="Rôles", value=txt, inline=False)
        if logs:
            hist = ""
            for log in logs[:3]:
                date = datetime.fromtimestamp(log[0])
                if date.date() == datetime.now().date():
                    if date.strftime("%H:%M") == datetime.now().strftime("%H:%M"):
                        hist += "• À l'instant · *{}*\n".format(log[1])
                    else:
                        hist += "• Aujourd'hui à {} · *{}*\n".format(date.strftime("%H:%M"), log[1])
                else:
                    hist += "• {} · *{}*\n".format(date.strftime("%d/%m/%Y"), log[0])
            em.add_field(name="Historique", value=hist, inline=False)
        if voice_channel:
            em.add_field(name="Actuellement sur", value=voice_channel, inline=False)
        # em.add_field(name="Rôles", value=" ".join(["`" + role.name + "`" for role in user.roles if not role.is_default()]) or "*Aucun*")
        if names:
            em.add_field(name="Pseudos", value=", ".join(names))
        if nicknames:
            em.add_field(name="Surnoms", value=", ".join(nicknames))
        em.set_footer(text=f"ID: {user.id} • Membre #{member_num}",
                      icon_url="https://ponyvilleplaza.com/files/img/boost.png" if booster_since else "")
        await ctx.send(embed=em)

        if self.bot.is_mod(user):
            notes = member["mod_notes"]
            if notes:
                ntxt = ""
                page = 1
                for n in notes:
                    chunk = "`{}` — {}: *{}*\n".format(
                        datetime.fromtimestamp(notes[n]["timestamp"]).strftime("%d/%m/%Y %H:%M"),
                        guild.get_member(notes[n]["author"]).mention, notes[n]["content"])
                    if len(ntxt) + len(chunk) > 2000:
                        mod = discord.Embed(title="Notes de modération", description=ntxt, color=user.color)
                        mod.set_footer(text=f"Page #{page}")
                        ntxt = chunk
                        page += 1
                        if await self.check_secure_channel(ctx.channel):
                            await ctx.send(embed=mod)
                        else:
                            await ctx.author.send(embed=mod)
                    else:
                        ntxt += chunk
                if ntxt:
                    mod = discord.Embed(title="Notes de modération", description=ntxt, color=user.color)
                    mod.set_footer(text=f"Page #{page}")
                    if await self.check_secure_channel(ctx.channel):
                        await ctx.send(embed=mod)
                    else:
                        await ctx.author.send(embed=mod)

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def showavatar(self, ctx, user: discord.User, size: int = 1024):
        """Affiche l'avatar de l'utilisateur visé

        [size] = Modifie la taille de l'avatar à afficher (def. 1024*1024)"""
        avatar_url = str(user.avatar_url_as(size=size))
        em = discord.Embed(title=str(user), color=user.color, description="<" + avatar_url + ">")
        em.set_image(url=avatar_url)
        await ctx.send(embed=em)

    @commands.command(name="updatestats")
    @checks.mod_or_permissions(administrator=True)
    @commands.bot_has_permissions(read_message_history=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def update_stats(self, ctx, days: int = 0):
        """Met à jour, du mieux que possible, les statistiques des membres de manière rétroactive

        <days> = Nombre de jours à regarder, par défaut tout ceux accessible (0)"""
        after = None
        members = {}
        await ctx.send("📈 **Mise à jour des stats.** — Ce processus peut mettre plusieurs heures si le volume de messages est important (> 1 million)")
        if days > 0:
            after = datetime.today() - timedelta(days=days)
        n = 0
        try:
            async for message in ctx.channel.history(limit=None, after=after, oldest_first=True):
                try:
                    author = message.author
                    if author.id not in members:
                        members[author.id] = message.created_at.timestamp()
                except:
                    pass
                n += 1
        except discord.Forbidden:
            await ctx.send("Je n'ai pas accès à tous les messages demandés")
        except discord.HTTPException:
            await ctx.send("Une erreur Discord m'empêche de continuer la mise à jour des statistiques")

        if members:
            records = await self.config.guild(ctx.guild).records()
            for member in members:
                records[member] = members[member]
            await self.config.guild(ctx.guild).records.set(records)
            await ctx.send("📈 **Mise à jour des stats.** — Réussie")
        else:
            await ctx.send("📈 **Mise à jour des stats.** — Echec (aucune donnée n'a été traitée)")


    @commands.group()
    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    async def notes(self, ctx):
        """Gestion des notes de modérateur sur les membres"""

    @notes.command(name="channel")
    async def secure_channel(self, ctx, channel: discord.TextChannel = None):
        """Indique un channel 'sécurisé' où peuvent être affichés publiquement les notes de modérateur

        Laisser vide pour retirer la sécurité.
        Par défaut, les notes sont envoyées en MP au modérateur qui réalise la commande dans les salons qui ne sont pas sécurités"""
        if channel:
            try:
                await self.config.guild(ctx.guild).get_raw("secure_channel")
            except KeyError:
                await self.config.guild(ctx.guild).set_raw("secure_channel", value=None)
            if channel.permissions_for(ctx.me).send_messages:
                await self.config.guild(ctx.guild).secure_channel.set(channel.id)
                await ctx.send("**Salon sécurisé ajouté** • Ce salon affichera les notes de modération publiquement.")
            else:
                await ctx.send("Je n'ai pas les droits pour écrire dans ce salon, modifiez cela avant de l'ajouter comme salon sécurisé.")
        else:
            await self.config.guild(ctx.guild).secure_channel.set(None)
            await ctx.send("**Salon sécurisé retiré** • Ce salon n'affichera plus les notes en public.")

    @notes.command(name="add")
    async def notes_add(self, ctx, user: discord.Member, *note):
        """Ajouter une note de modérateur à un membre"""
        if note:
            note = " ".join(note)
            num = len(await self.config.member(user).mod_notes()) + 1
            await self.config.member(user).mod_notes.set_raw(num, value={"content": note, "timestamp": time.time(),
                                                                         "author": ctx.author.id})
            await ctx.send(f"**Note #{num}** ajoutée avec succès.")
        else:
            await ctx.send("La note ne peut être vide. Pour éditer une note, utilisez `;notes edit`.")

    @notes.command(name="remove")
    async def notes_remove(self, ctx, user: discord.Member, num = None):
        """Retirer une note de modérateur d'un membre

        Ne pas remplir [num] affiche les notes et l'identifiant qui leur est lié"""
        if num:
            if num in await self.config.member(user).mod_notes():
                await self.config.member(user).mod_notes.clear_raw(num)
                await ctx.send(f"**Note #{num}** a été retirée pour ce membre")
                return
        txt = ""
        notes = await self.config.member(user).mod_notes()
        if notes:
            for note in notes:
                txt += "#{}. *{}*\n".format(note, notes[note]["content"])
            em = discord.Embed(title="Notes sur {}".format(str(user)), description=txt, color=await self.bot.get_embed_color(ctx.channel))
            em.set_footer(text="Tapez ;notes remove <num> pour retirer une de ces notes")
            if await self.check_secure_channel(ctx.channel):
                await ctx.send(embed=em)
            else:
                await ctx.author.send(embed=em)
        else:
            if await self.check_secure_channel(ctx.channel):
                await ctx.send("Il n'y a aucune note de modération sur ce membre")
            else:
                await ctx.author.send("Il n'y a aucune note de modération sur ce membre")

    @notes.command(name="check")
    async def notes_check(self, ctx, user: discord.Member):
        """Affiche les notes du membre et les identifiants liés à ceux-ci"""
        txt = ""
        notes = await self.config.member(user).mod_notes()
        if notes:
            for note in notes:
                txt += "#{}. *{}*\n".format(note, notes[note]["content"])
            em = discord.Embed(title="Notes sur {}".format(str(user)), description=txt,
                               color=await self.bot.get_embed_color(ctx.channel))
            em.set_footer(text="Tapez ;notes remove <num> pour retirer une de ces notes ou ;notes edit <num> pour en éditer une")
            if await self.check_secure_channel(ctx.channel):
                await ctx.send(embed=em)
            else:
                await ctx.author.send(embed=em)
        else:
            if await self.check_secure_channel(ctx.channel):
                await ctx.send("Il n'y a aucune note de modération sur ce membre")
            else:
                await ctx.author.send("Il n'y a aucune note de modération sur ce membre")

    @notes.command(name="edit")
    async def notes_edit(self, ctx, user: discord.Member, num, *note):
        """Modifier une note de modérateur d'un membre

        Utilisez `;notes check @user` pour voir les numéros liés aux différentes notes"""
        if num in await self.config.member(user).mod_notes():
            if note:
                note = " ".join(note)
                edited = await self.config.member(user).mod_notes.get_raw(num)
                if edited["author"] == ctx.author.id:
                    edited["content"] = note
                    edited["timestamp"] = time.time()
                    await self.config.member(user).mod_notes.set_raw(num, value=edited)
                    await ctx.send(f"**Note #{num}** éditée avec succès.")
                else:
                    await ctx.send("Seul l'auteur originel de la note peut la modifier")
            else:
                await ctx.send(f"La note ne peut pas être vide, pour la supprimer utilisez `;notes remove {num}`.")
        else:
            await ctx.send("Ce numéro de note est introuvable.")

    async def add_logs(self, user: discord.Member, desc: str):
        member =  self.config.member(user)
        async with member.logs() as logs:
            logs.append((time.time(), desc))
            if len(logs) > 10:
                await member.logs.set(logs[-10:])

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild:
            author = message.author
            last_day = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
            async with self.config.member(author).cons_days() as cons_days:
                if last_day in cons_days:
                    if datetime.now().strftime("%d/%m/%Y") not in cons_days:
                        cons_days.append(datetime.now().strftime("%d/%m/%Y"))
                elif datetime.now().strftime("%d/%m/%Y") not in cons_days:
                    await self.config.member(author).cons_days.set([datetime.now().strftime("%d/%m/%Y")])

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if isinstance(after, discord.Member):
            if after.name != before.name:
                await self.add_logs(after, f"Changement de pseudo » {after.name}")
                async with self.config.member(after).names() as names:
                    if after.name not in names:
                        names.append(after.name)
                        if len(names) > 20:
                            await self.config.member(after).names.set(names[-20:])
            if after.display_name != before.display_name:
                if after.display_name == after.name:
                    await self.add_logs(after, f"A retiré son surnom ({before.nick})")
                else:
                    await self.add_logs(after, f"Changement de surnom » {after.display_name}")
                    async with self.config.member(after).nicknames() as nicknames:
                        if after.nick not in nicknames:
                            nicknames.append(after.name)
                            if len(nicknames) > 20:
                                await self.config.member(after).nicknames.set(nicknames[-20:])
            if after.avatar_url != before.avatar_url:
                url = before.avatar_url.split("?")[0]
                await self.add_logs(after, f"Modification de l'avatar » [@]({url})")

    @commands.Cog.listener()
    async def on_member_join(self, user):
        await self.add_logs(user, "A rejoint le serveur")

    @commands.Cog.listener()
    async def on_member_remove(self, user):
        await self.add_logs(user, "A quitté le serveur")

    @commands.Cog.listener()
    async def on_member_ban(self, user):
        await self.add_logs(user, "A été banni")

    @commands.Cog.listener()
    async def on_member_unban(self, user):
        await self.add_logs(user, "A été débanni")

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        user = invite.inviter
        try:
            member = invite.guild.get_member(user.id)
            await self.add_logs(member, f"A créé une invitation » {invite.code}")
        except:
            pass