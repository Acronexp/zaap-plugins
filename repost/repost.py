import logging
import re
import time
from datetime import datetime, timedelta

import discord
from redbot.core import Config, checks, commands

logger = logging.getLogger("red.zaap-plugins.repost")

class Repost(commands.Cog):
    """Détecteur de repost et commandes associées"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)

        default_guild = {"link_reposts": True,
                         "immune_users": [],
                         "immune_channels": [],
                         "immune_roles": [],
                         "immune_links_strict": [],
                         "immune_links_starting": [],
                         "delete_reposts": False,
                         "reposts": {}}
        self.config.register_guild(**default_guild)
        self.immunity_cache = {}
        self.last_clean = None

    async def clean_reposts(self, guild: discord.Guild):
        if datetime.now().date() != self.last_clean:
            self.last_clean = datetime.now().date()
            reposts = await self.config.guild(guild).reposts()
            two_weeks = datetime.now() - timedelta(weeks=2)
            for repost in reposts:
                for e in reposts[repost]:
                    ts = datetime.fromtimestamp(e[2])
                    if ts < two_weeks:
                        reposts.remove(e)
                if not reposts[repost]:
                    del reposts[repost]
            await self.config.guild(guild).reposts.set(reposts)

    async def load_cache(self, guild: discord.Guild):
        self.immunity_cache[guild.id] = {"users": await self.config.guild(guild).immune_users(),
                                         "channels": await self.config.guild(guild).immune_channels(),
                                         "roles": await self.config.guild(guild).immune_roles(),
                                         "links_strict": await self.config.guild(guild).immune_links_strict(),
                                         "links_starting": await self.config.guild(guild).immune_links_starting()}
        return self.immunity_cache[guild.id]

    def normalize_link(self, base_link: str):
        is_yt = re.compile(r'https://www\.youtube\.com/watch\?v=([\w\-]*)', re.DOTALL | re.IGNORECASE).findall(base_link)
        if is_yt:
            return "https://youtu.be/{}".format(is_yt[0])
        is_tw = re.compile(r'https://twitter\.com/(?:\w *)/status /(?:\d *)(. *)', re.DOTALL | re.IGNORECASE).findall(base_link)
        if is_tw:
            return base_link.replace(is_tw[0], "") if is_tw[0] else base_link
        return base_link

    async def get_repost(self, message: discord.Message):
        guild = message.guild
        reposts = await self.config.guild(guild).reposts()
        for repost in reposts:
            for e in reposts[repost]:
                if e[0] == message.id:
                    return {"url": repost,
                            "cases": reposts[repost]}
        return {}

    async def message_immune(self, message: discord.Message):
        guild = message.guild
        if guild.id not in self.immunity_cache:
            await self.load_cache(guild)
        cache = self.immunity_cache[guild.id]
        if message.author.id in cache["users"] or message.channel.id in cache["channels"]:
            return True
        elif [r for r in cache["roles"] if r in [n.id for n in message.author.roles]]:
            return True
        return False

    async def link_immune(self, guild: discord.Guild, link: str):
        if guild.id not in self.immunity_cache:
            await self.load_cache(guild)
        cache = self.immunity_cache[guild.id]
        if link in cache["links_strict"]:
            return True
        elif [l for l in cache["links_starting"] if link.startswith(l)]:
            return True
        return False

    @commands.group(name="repost")
    @checks.admin_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def _repost(self, ctx):
        """Paramètres du détecteur de reposts"""

    @_repost.command()
    async def toggle(self, ctx):
        guild = ctx.guild
        if not await self.config.guild(guild).link_reposts():
            await self.config.guild(guild).link_reposts.set(True)
            await ctx.send("**Activé** • Le détecteur de reposts de liens est activé.")
        else:
            await self.config.guild(guild).link_reposts.set(False)
            await ctx.send("**Désactivé** • Le détecteur de reposts de liens est désactivé.")

    @_repost.command(hidden=True)
    async def reset(self, ctx):
        guild = ctx.guild
        await self.config.guild(guild).reposts.set({})
        await ctx.send("**Reset effectué**")

    @_repost.command(name="delete")
    async def delete_repost(self, ctx):
        """Activer/désactiver la suppression des messages considérés comme des reposts"""
        guild = ctx.guild
        if not await self.config.guild(guild).delete_reposts():
            await self.config.guild(guild).delete_reposts.set(True)
            await ctx.send("**Activé** • Les reposts seront automatiquement supprimés.")
        else:
            await self.config.guild(guild).delete_reposts.set(False)
            await ctx.send("**Désactivé** • Les reposts ne seront plus supprimés automatiquement.")

    @commands.group(name="immune")
    async def _repost_immune(self, ctx):
        """Paramètres concernant l'immunité au détecteur de reposts"""

    @_repost_immune.command()
    async def user(self, ctx, user: discord.Member):
        """Ajouter ou retirer une immunité pour un membre"""
        guild = ctx.guild
        liste = await self.config.guild(guild).immune_users()
        if user.id not in liste:
            liste.append(user.id)
            await self.config.guild(guild).immune_users.set(liste)
            await ctx.send(f"**Immunisé** • {user.name} est désormais immunisé au détecteur de reposts.")
        else:
            liste.remove(user.id)
            await self.config.guild(guild).immune_users.set(liste)
            await ctx.send(f"**Retiré des immunisés** • {user.name} n'est désormais plus immunisé au détecteur de reposts.")
        await self.load_cache(guild)

    @_repost_immune.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Ajouter ou retirer une immunité pour un salon écrit"""
        guild = ctx.guild
        liste = await self.config.guild(guild).immune_channels()
        if channel.id not in liste:
            liste.append(channel.id)
            await self.config.guild(guild).immune_channels.set(liste)
            await ctx.send(f"**Immunisé** • Les reposts sur {channel.mention} ne seront plus notifiés.")
        else:
            liste.remove(channel.id)
            await self.config.guild(guild).immune_channels.set(liste)
            await ctx.send(f"**Retiré des immunisés** • Les reposts sur {channel.mention} seront de nouveau notifiés.")
        await self.load_cache(guild)

    @_repost_immune.command()
    async def role(self, ctx, role: discord.Role):
        """Ajouter ou retirer une immunité pour un rôle (donc les membres possédant ce rôle)"""
        guild = ctx.guild
        liste = await self.config.guild(guild).immune_roles()
        if role.id not in liste:
            liste.append(role.id)
            await self.config.guild(guild).immune_roles.set(liste)
            await ctx.send(f"**Immunisé** • Les membres ayant le rôle {role.name} sont désormais immunisés contre le détecteur de reposts.")
        else:
            liste.remove(role.id)
            await self.config.guild(guild).immune_roles.set(liste)
            await ctx.send(f"**Retiré des immunisés** • Les membres ayant le rôle {role.name} ne sont plus immunisés du détecteur de reposts.")
        await self.load_cache(guild)

    @_repost_immune.command()
    async def link(self, ctx, lien: str):
        """Ajouter ou retirer l'immunité pour un lien, strictement ou non

        Si vous ajoutez une étoile à la fin du lien, ce sera tous les liens commençant par ce qu'il y a avant l'étoile qui ne seront pas comptés comme reposts
        __Exemples :__
        `;repost immune link https://discord.me/qqchose` => immunise seulement le lien `https://discord.me/qqchose`
        `;repost immune link https://discord.me/*` => immunise tous les liens commençant par `https://discord.me/`"""
        guild = ctx.guild
        if lien == "https://www.youtube.com/*":
            lien = "https://youtu.be/*"

        if lien.endswith("*"):
            lien = lien[:-1]
            liste = await self.config.guild(guild).immune_links_starting()
            if lien not in liste:
                liste.append(lien)
                await self.config.guild(guild).immune_links_starting.set(liste)
                await ctx.send(
                    f"**Immunisé** • Les liens commençant par `{lien}` ne seront plus comptés comme des reposts.")
            else:
                liste.remove(lien)
                await self.config.guild(guild).immune_links_starting.set(liste)
                await ctx.send(
                    f"**Plus immunisé** • Les liens commençant par `{lien}` ne sont plus immunisés.")
        else:
            liste = await self.config.guild(guild).immune_links_strict()
            if lien not in liste:
                liste.append(lien)
                await self.config.guild(guild).immune_links_strict.set(liste)
                await ctx.send(
                    f"**Immunisé** • Le lien `{lien}` ne pourra plus figurer dans les reposts.")
            else:
                liste.remove(lien)
                await self.config.guild(guild).immune_links_strict.set(liste)
                await ctx.send(
                    f"**Plus immunisé** • Le lien `{lien}` n'est plus immunisé aux reposts.")
        await self.load_cache(guild)

    @_repost_immune.command(name="list")
    async def immune_list(self, ctx):
        """Liste les éléments immunisés contre le détecteur de reposts"""
        guild = ctx.guild
        em = discord.Embed(title="Elements immunisés contre le détecteur de reposts", color=await ctx.embed_color())
        if await self.config.guild(guild).immune_users():
            txt = ""
            for u in await self.config.guild(guild).immune_users():
                user = guild.get_member(u)
                txt += f"- {user.mention}\n"
            em.add_field(name="Membres", value=txt)
        if await self.config.guild(guild).immune_roles():
            txt = ""
            for r in await self.config.guild(guild).immune_roles():
                role = guild.get_role(r)
                txt += f"- {role.mention}\n"
            em.add_field(name="Rôles", value=txt)
        if await self.config.guild(guild).immune_channels():
            txt = ""
            for c in await self.config.guild(guild).immune_channels():
                channel = guild.get_channel(c)
                txt += f"- {channel.mention}\n"
            em.add_field(name="Salons écrits", value=txt)
        links = ""
        if await self.config.guild(guild).immune_links_strict():
            for l in await self.config.guild(guild).immune_links_strict():
                links += f"- `{l}`\n"
        if await self.config.guild(guild).immune_links_starting():
            for l in await self.config.guild(guild).immune_links_starting():
                links += f"- `{l}*`\n"
        if links:
            em.add_field(name="Liens", value=links)
            em.set_footer(text="Les liens terminant par * filtrent tous les liens commençant par ceux-ci")
        await ctx.send(embed=em)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild:
            guild = message.guild
            if await self.config.guild(guild).link_reposts():
                content = message.content
                if "http" in content and not await self.message_immune(message):
                    scan = re.compile(r'(https?://\S*\.\S*)', re.DOTALL | re.IGNORECASE).findall(content)
                    if scan:
                        url = self.normalize_link(scan[0])
                        if not await self.link_immune(guild, url):
                            if url in await self.config.guild(guild).reposts():
                                repost = await self.config.guild(guild).reposts.get_raw(url)
                                repost.append((message.id, message.channel.id, time.time()))
                                await self.config.guild(guild).reposts.set_raw(url, value=repost)
                                if await self.config.guild(guild).delete_reposts():
                                    try:
                                        await message.delete()
                                    except:
                                        raise PermissionError(f"Impossible de supprimer le message {message.id}")
                                else:
                                    try:
                                        await message.add_reaction("♻️")
                                    except:
                                        raise PermissionError(f"Impossible d'ajouter un emoji au message {message.id}")
                            else:
                                repost = [(message.id, message.channel.id, time.time())]
                                await self.config.guild(guild).reposts.set_raw(url, value=repost)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if isinstance(user, discord.Member):
            if not user.bot:
                message = reaction.message
                guild = message.guild
                if await self.config.guild(guild).link_reposts() and reaction.emoji == "♻️":
                    repost = await self.get_repost(message)
                    if repost:
                        txt = ""
                        for r in repost["cases"]:
                            channel = self.bot.get_channel(r[1])
                            msg = await channel.fetch_message(r[0])
                            if not txt:
                                txt += "**Original** ─ [{} par {}]({})\n".format(msg.created_at.strftime("%d/%m/%Y %H:%M"), msg.author.name,
                                                             msg.jump_url)
                            else:
                                txt += "• [{} par {}]({})\n".format(msg.created_at.strftime("%d/%m/%Y %H:%M"), msg.author.name,
                                                              msg.jump_url)
                        em = discord.Embed(title="Reposts de \"{}\"".format(repost["url"]), description=txt,
                                           color=await self.bot.get_embed_color(message.channel))
                        try:
                            await user.send(embed=em)
                            await message.remove_reaction("♻️", user)
                        except:
                            pass




