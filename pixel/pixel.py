import asyncio
import logging
import operator
import os
import random
import re
import time
from datetime import datetime
from urllib.parse import urlsplit

import aiofiles
import aiohttp
import discord
import requests
from redbot.core import Config, checks, commands
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.menus import start_adding_reactions

logger = logging.getLogger("red.zaap-plugins.pixel")

class PixelError(Exception):
    pass

class ExtensionNotSupported(PixelError):
    pass

class MaxFileSize(PixelError):
    pass

class MaxFolderSize(PixelError):
    pass

class DownloadError(PixelError):
    pass

class Pixel(commands.Cog):
    """Stockage de stickers personnalisés"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        folder = cog_data_path(self) / f"local"
        folder.mkdir(exist_ok=True, parents=True)
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        default_global = {"FOLDER_MAX_SIZE": 25e7, # 250 MB / guild
                          "FILE_MAX_SIZE": 1e7} # 10 MB / file
        default_guild = {"SETTINGS": {"need_approb": True,
                                      "channels_blacklist": [],
                                      "users_blacklist": [],
                                      "antiflood": True},
                         "WAITING": [],
                         "FILES": []}
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.cooldown = {}


    def _get_folder_size(self, path):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return int(total_size)

    def _get_local_file_size(self, path):
        if os.path.exists(path):
            return int(os.path.getsize(path))
        return 0

    def _get_file_length(self, url):
        h = requests.head(url, allow_redirects=True)
        header = h.headers
        content_length = header.get('content-length', None)
        if content_length:
            return content_length
        else:
            return None

    def _get_file_type(self, url):
        h = requests.head(url, allow_redirects=True)
        header = h.headers
        content_type = header.get('content-type')
        return content_type.split("/")[0]

    def humanize_size(self, b: int):
        if b > 1000:
            kb = round(b / 1e3, 2)
            if kb > 1000:
                mb = round(b / 1e6, 2)
                return f"{mb} MB"
            return f"{kb} KB"
        return f"{b} B"


    async def get_file(self, guild: discord.Guild, name: str) -> dict:
        for file in await self.config.guild(guild).FILES():
            if file["name"] == name:
                return file
        return {}

    async def files_list(self, guild: discord.Guild):
        data = await self.config.guild(guild).FILES()
        return [i["name"] for i in data]


    async def get_waiting(self, guild: discord.Guild, name: str) -> dict:
        for file in await self.config.guild(guild).WAITING():
            if file["name"] == name:
                return file
        return {}

    async def waiting_list(self, guild: discord.Guild):
        data = await self.config.guild(guild).WAITING()
        return [i["name"] for i in data]

    async def get_similars(self, guild: discord.Guild, base_name: str):
        data = await self.config.guild(guild).FILES()
        similars = []
        for file in data:
            if file["name"].startswith(base_name):
                similars.append(file)
        return similars

    async def find_disp_name(self, guild: discord.Guild, base_name: str):
        similars = await self.get_similars(guild, base_name)
        if similars:
            n = 2
            name = f"{base_name}{n}"
            while name in [file["name"] for file in similars]:
                n += 1
                name = f"{base_name}{n}"
            return name
        return base_name

    async def guild_path(self, guild: discord.Guild):
        gid = str(guild.id)
        path = cog_data_path(self) / f"local/{gid}"
        if not path.is_dir():
            path.mkdir(exist_ok=True, parents=True)
        return path

    async def download_attachment(self, msg: discord.Message, name: str):
        guild = msg.guild
        path = await self.guild_path(guild)
        seed = str(int(time.time()))
        ext = os.path.splitext(msg.attachments[0].filename)[1]
        if ext.lower() in [".jpeg", ".jpg", ".png", ".gif", ".gifv", ".mp3", ".wav", ".mp4", ".webm", ".txt"]:
            if msg.attachments[0].size <= await self.config.FILE_MAX_SIZE():
                if msg.attachments[0].size + self._get_folder_size(str(path)) <= await self.config.FOLDER_MAX_SIZE():
                    filename = "{}_{}".format(seed, msg.attachments[0].filename)
                    filepath = "{}/{}".format(str(path), filename)

                    data = await self.config.guild(guild).FILES()
                    new = {"name": name,
                           "path": filepath,
                           "url": msg.attachments[0].url,
                           "author": msg.author.id,
                           "creation": time.time(),
                           "count": 0}
                    data.append(new)
                    await msg.attachments[0].save(filepath)
                    await self.config.guild(guild).FILES.set(data)
                else:
                    raise MaxFolderSize()
            else:
                raise MaxFileSize()
        else:
            raise ExtensionNotSupported()

    async def replace_download(self, guild: discord.Guild, name: str, url: str):
        path = await self.guild_path(guild)
        seed = str(int(time.time()))
        file_name, ext = os.path.splitext(os.path.basename(urlsplit(url).path))
        file_size = float(self._get_file_length(url))
        if name in await self.files_list(guild) + await self.waiting_list(guild):
            if ext.lower() in [".jpeg", ".jpg", ".png", ".gif", ".gifv", ".mp3", ".wav", ".mp4", ".webm", ".txt"]:
                if file_size <= await self.config.FILE_MAX_SIZE():
                    if file_size +  self._get_folder_size(str(path)) <= await self.config.FOLDER_MAX_SIZE():
                        filename = "{}_{}".format(seed, file_name)
                        filepath = "{}/{}".format(str(path), filename)

                        async with aiohttp.ClientSession() as session:
                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    f = await aiofiles.open(str(filepath), mode='wb')
                                    await f.write(await resp.read())
                                    await f.close()
                                else:
                                    raise DownloadError()

                        file = await self.get_file(guild, name)
                        data = await self.config.guild(guild).FILES()
                        index = data.index(file)
                        file["path"] = filepath
                        data[index] = file
                        await self.config.guild(guild).FILES.set(data)
                    else:
                        raise MaxFolderSize()
                else:
                    raise MaxFileSize()
            else:
                raise ExtensionNotSupported()
        else:
            raise NameError()

    def any_num(self, s):
        return any(i.isdigit() for i in s)

    @commands.group(name="pix")
    @commands.guild_only()
    async def _pixel(self, ctx):
        """Gestion des fichiers personnalisés du serveur"""

    @_pixel.command(name="add")
    @commands.cooldown(1, 10, commands.BucketType.member)
    async def pixel_add(self, ctx, name: str, url = None):
        """Ajouter ou proposer un fichier personnalisé (image, texte, audio ou vidéo)

        __Types supportés :__ jpeg, jpg, png, gif(v), mp3, wav, mp4, webm et txt
        Si aucune URL n'est donnée, prendra le fichier importé sur Discord avec la commande"""
        author, guild = ctx.author, ctx.guild
        em_color = await ctx.embed_color()
        if ":" in name:
            await ctx.send("**Nom invalide** • Ne mettez pas `:` autour du nom lorsque vous proposez un fichier.")
            return
        if name.lower() in ["list", "liste"]:
            await ctx.send("**Nom réservé** • Ce nom est déjà utilisé par le bot pour des fonctionnalités spécifiques.")
            return
        if name in await self.files_list(guild):
            base = re.compile(r"([A-z]+)(\d*)?", re.DOTALL | re.IGNORECASE).findall(name)[0][0]
            if base != name:
                new_name = await self.find_disp_name(guild, base)
            else:
                new_name = f"{name}2"
            await ctx.send("**Nom indisponible** • Un fichier porte déjà ce nom sur ce serveur.\n"
                           "Si c'est celui-ci que vous voulez modifier, utilisez `;pix edit {}`.\n"
                           "Sinon, sachez que le nom ***{}*** est disponible.".format(name, new_name))
            return
        if author.permissions_in(ctx.channel).administrator or author.permissions_in(ctx.channel).manage_messages \
                and await self.config.guild(guild).SETTINGS.get_raw("need_approb"):
            if name in await self.waiting_list(guild):
                waiting = await self.config.guild(guild).WAITING()
                files = await self.config.guild(guild).FILES()
                file = await self.get_waiting(guild, name)
                waiting.remove(file)
                files.append(file)
                await self.config.guild(guild).WAITING.set(waiting)
                await self.config.guild(guild).FILES.set(files)
                em = discord.Embed(description="Fichier `{}` proposé par {} approuvé par {}".format(
                    file["name"], guild.get_member(file["author"]).mention, author.mention), color=em_color)
                em.set_image(url=file["url"])
                await ctx.send(embed=em)
            elif url:
                if self._get_file_type(url) in ["image", "audio", "video"]:
                    data = await self.config.guild(guild).FILES()
                    new = {"name": name,
                           "path": None,
                           "url": url,
                           "author": author.id,
                           "creation": time.time(),
                           "count": 0}
                    data.append(new)
                    await self.config.guild(guild).FILES.set(data)
                    em = discord.Embed(description=f"Fichier `{name}` ajouté avec succès", color=em_color)
                    em.set_image(url=url)
                    em.set_footer(text=f"Utilisez-le avec :{name}: sur les salons autorisés")
                    await ctx.send(embed=em)
                else:
                    await ctx.send("**URL invalide** • Le type de fichier que contient l'URL est incompatible avec "
                                   "ce qui est supporté par le bot ou Discord.")
            elif ctx.message.attachments:
                try:
                    async with ctx.channel.typing():
                        await self.download_attachment(ctx.message, name)
                    await ctx.send(f"Fichier `{name}` ajouté avec succès\nUtilisez-le avec :{name}:.")
                    file = await self.get_file(guild, name)
                    await ctx.send(files=[discord.File(file["path"])])
                except MaxFolderSize:
                    await ctx.send("**Taille maximale du dossier atteinte** • Retirez quelques fichiers parmis ceux "
                                   "qui sont enregistrés en local avant d'en ajouter d'autres.")
                    return
                except MaxFileSize:
                    await ctx.send("**Taille maximale du fichier atteinte** • Ce fichier dépasse la limite imposée de {}.".format(self.humanize_size(await self.config.FILE_MAX_SIZE())))
                    return
                except ExtensionNotSupported:
                    await ctx.send("**Extension non supportée** • Consultez la liste dans l'aide de la commande "
                                   "(`;help pix add`)")
                    return
            else:
                await ctx.send("**Aucun fichier** • Fournissez un fichier pour l'ajouter (URL ou directement téléchargé sur Discord)")
        elif url:
            data = await self.config.guild(guild).WAITING()
            new = {"name": name,
                   "path": None,
                   "url": url,
                   "author": author.id,
                   "creation": time.time(),
                   "count": 0}
            data.append(new)
            await self.config.guild(guild).WAITING.set(data)
            em = discord.Embed(description=f"Fichier `{name}` proposé. Un administrateur ou un membre avec la "
                                           f"permission `manage_message` doit l'approuver avec `;pix add {name}`.", color=em_color)
            em.set_image(url=url)
            await ctx.send(embed=em)
        elif ctx.message.attachments:
            try:
                await self.download_attachment(ctx.message, name)
                await ctx.send(f"Fichier `{name}` téléchargé et proposé. Un administrateur ou un membre avec la "
                                           f"permission `manage_message` doit l'approuver avec `;pix add {name}`.")
            except MaxFolderSize:
                await ctx.send("**Taille maximale du dossier atteinte** • Impossible de proposer un fichier sous cette "
                               "forme. Utilisez plutôt une URL d'un fichier stocké sur un site d'hébergement.")
                return
            except MaxFileSize:
                await ctx.send("**Taille maximale du dossier atteinte** • Impossible de proposer un fichier sous cette "
                               "forme. Utilisez plutôt une URL d'un fichier stocké sur un site d'hébergement.")
                return
            except ExtensionNotSupported:
                await ctx.send("**Extension non supportée** • Consultez la liste dans l'aide de la commande "
                               "(`;help pix add`)")
                return
        else:
            await ctx.send(
                "**Aucun fichier proposé** • Fournissez un fichier pour le proposer "
                "(URL ou directement téléchargé sur Discord)")

    @_pixel.command(name="remove")
    @checks.admin_or_permissions(manage_messages=True)
    @commands.cooldown(1, 10, commands.BucketType.member)
    async def pixel_remove(self, ctx, name: str):
        """Retirer un fichier personnalisé"""
        author, guild = ctx.author, ctx.guild
        if ":" in name:
            await ctx.send("**Nom invalide** • Ne mettez pas `:` autour du nom.")
            return
        if name in await self.files_list(guild):
            tb = ""
            file = await self.get_file(guild, name)
            data = await self.config.guild(guild).FILES()
            if file["path"]:
                try:
                    os.remove(file["path"])
                    tb += "- Fichier local supprimé\n"
                    data = await self.config.guild(guild).FILES()
                    index = data.index(file)
                    file["path"] = None
                    data[index] = file
                    await self.config.guild(guild).FILES.set(data)
                except Exception:
                    logger.error(f"Impossible de supprimer {name}", exc_info=True)
                    tb += "- Fichier local non supprimé\n"
                    pass
            else:
                tb += "- Aucun fichier local\n"
            data.remove(file)
            tb += f"- Données liées à `{name}` supprimées\n"
            await self.config.guild(guild).FILES.set(data)
            await ctx.send(tb)
        elif name in await self.waiting_list(guild):
            wait = await self.get_waiting(guild, name)
            data = await self.config.guild(guild).WAITING()
            data.remove(wait)
            await self.config.guild(guild).FILES.set(data)
            await ctx.send("**Proposition refusée** • Proposition de {} pour `{}` supprimée.".format(guild.get_member(
                wait["author"]).mention, name))
        else:
            await ctx.send("**Nom introuvable** • Vérifiez l'orthographe et la casse.")

    @_pixel.command(name="edit")
    @checks.admin_or_permissions(manage_messages=True)
    @commands.cooldown(1, 10, commands.BucketType.member)
    async def pixel_edit(self, ctx, name: str):
        """Retirer un fichier personnalisé"""
        author, guild = ctx.author, ctx.guild
        em_color = await ctx.embed_color()
        if ":" in name:
            await ctx.send("**Nom invalide** • Ne mettez pas `:` autour du nom.")
            return
        if name in await self.files_list(guild):
            file = {}
            while True:
                file = await self.get_file(guild, file["name"] if file else name)
                name = file["name"]
                local_txt = "Supprimer/Retélécharger" if file["path"] else "Télécharger depuis URL"
                size = self.humanize_size(self._get_local_file_size(file["path"])) if file["path"] else "Non téléchargé"
                crea = datetime.fromtimestamp(file["creation"]).strftime("%d/%m/%Y")
                auth = guild.get_member(file["author"]).mention
                count = file["count"]
                infos = f"**Taille** » {size}\n" \
                        f"**Date de création** » {crea}\n" \
                        f"**Auteur** » {auth}\n" \
                        f"**Utilisations** » {count}"
                options_txt = "🏷️ · Modifier le nom\n" \
                              "🔗 · Modifier l'[URL]({})\n" \
                              "💾 · Gestion du fichier local ({})\n" \
                              "❌ · Quitter".format(file["url"], local_txt)
                emojis = ["🏷", "🔗", "💾", "❌"]
                em = discord.Embed(title=f"Édition de fichier » :{name}:", description=infos, color=em_color)
                em.add_field(name="Navigation", value=options_txt, inline=False)
                em.set_footer(text="Cliquez sur la réaction correspondante à l'action voulue")
                msg = await ctx.send(embed=em)
                start_adding_reactions(msg, emojis)
                try:
                    logger.info("En attente de réaction...")
                    react, user = await self.bot.wait_for("reaction_add",
                                                          check=lambda r, u: u == author and r.message.id == msg.id,
                                                          timeout=30)
                except asyncio.TimeoutError:
                    await msg.delete()
                    return
                else:
                    logger.info("Réaction détectée. Traitement...")
                    emoji = react.emoji
                if emoji == "🏷":
                    await msg.delete()
                    em = discord.Embed(title=f"Édition de fichier » :{name}:",
                                       description="Quel nouveau nom voulez-vous attribuer à ce fichier ?", color=em_color)
                    em.set_footer(text="Le nom ne doit pas contenir de caractères spéciaux (dont ':') ou d'espaces")
                    msg = await ctx.send(embed=em)

                    def check(msg: discord.Message):
                        return msg.author == ctx.author and ":" not in msg.content

                    try:
                        resp = await self.bot.wait_for("message", check=check, timeout=30)
                    except asyncio.TimeoutError:
                        await msg.delete()
                        continue

                    new_name = resp.content.replace(" ", "")
                    if new_name != file["name"]:
                        if new_name not in await self.files_list(guild) + await self.waiting_list(guild):
                            data = await self.config.guild(guild).FILES()
                            index = data.index(file)
                            file["name"] = new_name
                            data[index] = file
                            await self.config.guild(guild).FILES.set(data)
                            await ctx.send("Modification réalisée avec succès.", delete_after=10)
                        else:
                            await ctx.send("Nom déjà utilisé. Retour au menu...", delete_after=10)
                    else:
                        await ctx.send("Nom identique à l'actuel. Retour au menu...", delete_after=10)
                elif emoji == "🔗":
                    await msg.delete()
                    em = discord.Embed(title=f"Édition de fichier » :{name}:",
                                       description="Fournissez une nouvelle URL valide pour le fichier.", color=em_color)
                    em.set_footer(text="Utilisez de préférence Imgur et ayez un lien contenant l'extension du fichier")
                    msg = await ctx.send(embed=em)

                    def check(msg: discord.Message):
                        return msg.author == ctx.author

                    try:
                        resp = await self.bot.wait_for("message", check=check, timeout=120)
                    except asyncio.TimeoutError:
                        await msg.delete()
                        continue

                    if self._get_file_type(resp.content) in ["image", "audio", "video"]:
                        data = await self.config.guild(guild).FILES()
                        index = data.index(file)
                        file["url"] = resp.content
                        data[index] = file
                        await self.config.guild(guild).FILES.set(data)
                        await ctx.send("Modification réalisée avec succès.\n"
                                       "Si le fichier à afficher n'est plus le même que précédemment, pensez à utiliser "
                                       "l'option *Retélécharger* dans le menu.", delete_after=15)
                    else:
                        await ctx.send("Le fichier contenu dans l'URL donnée n'est pas supporté par le bot "
                                       "ou Discord.", delete_after=10)
                elif emoji == "💾":
                    await msg.delete()
                    while True:
                        file = await self.get_file(guild, file["name"])
                        if file["path"]:
                            options_txt = "🔄 · Retélécharger depuis l'[URL]({})\n" \
                                          "🧹 · Supprimer le fichier local ({})\n" \
                                          "❌ · Retour au menu".format(file["url"], file["path"].split("/")[-1])
                            em = discord.Embed(title=f"Édition de fichier » :{name}:",
                                               description=options_txt, color=em_color)
                            em.set_footer(text="Cliquez sur l'emoji correspondant à l'action que vous voulez réaliser")
                            msg = await ctx.send(embed=em)
                            emojis = ["🔄", "🧹", "❌"]

                            start_adding_reactions(msg, emojis)
                            try:
                                react, user = await self.bot.wait_for("reaction_add", check=lambda r, u: u == author and r.message.id == msg.id, timeout=30)
                            except asyncio.TimeoutError:
                                await msg.delete()
                                return
                            else:
                                emoji = react.emoji

                            if emoji == "🔄":
                                await msg.delete()
                                try:
                                    async with ctx.channel.typing():
                                        try:
                                            os.remove(file["path"])
                                            await ctx.send("Ancien fichier local supprimé avec succès", delete_after=10)
                                        except Exception:
                                            logger.error(f"Impossible de supprimer {name}", exc_info=True)
                                        await self.replace_download(guild, file["name"], file["url"])
                                    await ctx.send("Retéléchargement depuis URL réalisé avec succès.", delete_after=10)
                                except MaxFolderSize:
                                    await ctx.send(
                                        "**Taille maximale du dossier atteinte** • Supprimez quelques "
                                        "fichiers stockés localement d'abord.", delete_after=20)
                                    continue
                                except MaxFileSize:
                                    await ctx.send(
                                        "**Taille maximale du fichier atteinte** • Le fichier pointé par l'URL est trop lourd, réessayez avec un fichier plus petit que {}.".format(
                                            self.humanize_size(await self.config.FILE_MAX_SIZE())), delete_after=20)
                                    continue
                                except ExtensionNotSupported:
                                    await ctx.send(
                                        "**Extension non supportée** • Consultez la liste dans l'aide de la commande d'ajout"
                                        "(`;help pix add`)", delete_after=20)
                                    continue
                                except NameError:
                                    await ctx.send(
                                        "**Erreur** • Le nom fourni est le mauvais, "
                                        "cette erreur ne devrait pas arriver à moins que le stockage soit corrompu", delete_after=20)
                                    continue
                                except DownloadError:
                                    await ctx.send(
                                        "**Erreur de téléchargement** • Changez l'URL et réessayez", delete_after=20)
                                    logger.error("Impossible de télécharger depuis {}".format(file["url"]), exc_info=True)
                                    continue

                            elif emoji == "🧹":
                                await msg.delete()
                                file = await self.get_file(guild, file["name"])
                                if file["path"]:
                                    try:
                                        os.remove(file["path"])
                                        await ctx.send("Fichier local supprimé avec succès", delete_after=10)
                                    except Exception:
                                        logger.error(f"Impossible de supprimer {name}", exc_info=True)
                                        await ctx.send("Impossible de supprimer le fichier local.\n"
                                                       "Le chemin sera tout de même effacé pour éviter les conflits.", delete_after=15)
                                    data = await self.config.guild(guild).FILES()
                                    index = data.index(file)
                                    file["path"] = None
                                    data[index] = file
                                    await self.config.guild(guild).FILES.set(data)
                                else:
                                    await ctx.send("Il n'y a aucun fichier local à supprimer", delete_after=10)

                            else:
                                await msg.delete()
                                break
                        else:
                            options_txt = "📥 · Télécharger depuis l'[URL]({})\n" \
                                          "❌ · Retour au menu".format(file["url"])
                            em = discord.Embed(title=f"Édition de fichier » :{name}:",
                                               description=options_txt, color=em_color)
                            em.set_footer(text="Cliquez sur l'emoji correspondant à l'action que vous voulez réaliser")
                            msg = await ctx.send(embed=em)
                            emojis = ["📥", "❌"]

                            start_adding_reactions(msg, emojis)
                            try:
                                react, user = await self.bot.wait_for("reaction_add", check=lambda r, u: u == author and r.message.id == msg.id, timeout=30)
                            except asyncio.TimeoutError:
                                await msg.delete()
                                return
                            else:
                                emoji = react.emoji

                            if emoji == "📥":
                                await msg.delete()
                                try:
                                    await self.replace_download(guild, file["name"], file["url"])
                                    await ctx.send("Téléchargement réalisé avec succès.", delete_after=10)
                                except MaxFolderSize:
                                    await ctx.send(
                                        "**Taille maximale du dossier atteinte** • Supprimez quelques "
                                        "fichiers stockés localement d'abord.", delete_after=20)
                                    continue
                                except MaxFileSize:
                                    await ctx.send(
                                        "**Taille maximale du fichier atteinte** • Le fichier pointé par l'URL est trop lourd, réessayez avec un fichier plus petit que {}.".format(
                                            self.humanize_size(await self.config.FILE_MAX_SIZE())), delete_after=20)
                                    continue
                                except ExtensionNotSupported:
                                    await ctx.send(
                                        "**Extension non supportée** • Consultez la liste dans l'aide de la commande d'ajout"
                                        "(`;help pix add`)", delete_after=20)
                                    continue
                                except NameError:
                                    await ctx.send(
                                        "**Erreur** • Le nom fourni est le mauvais, "
                                        "cette erreur ne devrait pas arriver à moins que le stockage soit corrompu",
                                        delete_after=20)
                                    continue
                                except DownloadError:
                                    await ctx.send(
                                        "**Erreur de téléchargement** • Changez l'URL et réessayez", delete_after=20)
                                    logger.error("Impossible de télécharger depuis {}".format(file["url"]),
                                                 exc_info=True)
                                    continue
                            else:
                                await msg.delete()
                                break
                else:
                    await msg.delete()
                    return
        else:
            await ctx.send("**Fichier inconnu** • Vérifiez le nom que vous avez fourni.\n"
                           "Sachez que cette commande ne fonctionne pas pour les fichiers en attente d'approbation.")


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild:
            content = message.content
            guild = message.guild
            files = await self.config.guild(guild).FILES()
            if files:
                if ":" in content:
                    channel, author = message.channel, message.author
                    if author.bot:
                        return
                    if author.id not in await self.config.guild(guild).SETTINGS.get_raw("users_blacklist"):
                        if channel.id not in await self.config.guild(guild).SETTINGS.get_raw("channels_blacklist"):
                            regex = re.compile(r'([\w?]+)?:(.*?):', re.DOTALL | re.IGNORECASE).findall(content)
                            if regex:
                                em_color = await self.bot.get_embed_color(channel)
                                for param, name in regex:
                                    if name in await self.files_list(guild):
                                        if name in [e.name for e in guild.emojis]:
                                            continue

                                        file = await self.get_file(guild, name)
                                        suppr = False
                                        if param:
                                            if "b" in param: # Donner le fichier lié à la "base" du nom
                                                base = re.compile(r"([A-z]+)(\d*)?", re.DOTALL | re.IGNORECASE).findall(name)[0][0]
                                                new_file = await self.get_file(guild, base)
                                                if new_file:
                                                    file = new_file
                                            if "s" in param: # Affiche un menu avec tous les fichiers de noms similaires
                                                base = \
                                                re.compile(r"([A-z]+)(\d*)?", re.DOTALL | re.IGNORECASE).findall(name)[
                                                    0][0]
                                                similars = await self.get_similars(guild, base)
                                                if len(similars) > 1:
                                                    index = 0
                                                    msg = None
                                                    while True:
                                                        if index < 0:
                                                            index = len(similars) - 1
                                                        elif index == len(similars):
                                                            index = 0

                                                        em = discord.Embed(title=f"Fichiers similaires » {base}",
                                                                           description="`:{}:`".format(similars[index]["name"]), color=em_color)
                                                        em.set_image(url=similars[index]["url"])
                                                        em.set_footer(
                                                            text=f"#{index} • Naviguez entre les pages avec les emojis ci-dessous")
                                                        if not msg:
                                                            msg = await channel.send(embed=em)
                                                        else:
                                                            await msg.edit(embed=em)
                                                        emojis = ["⬅", "❌", "➡"]
                                                        start_adding_reactions(msg, emojis)
                                                        try:
                                                            react, user = await self.bot.wait_for("reaction_add",
                                                                                                  check=lambda r, u: u == author and r.message.id == msg.id,
                                                                                                  timeout=30)
                                                        except asyncio.TimeoutError:
                                                            await msg.delete()
                                                            return
                                                        else:
                                                            emoji = react.emoji

                                                        if emoji == "⬅":
                                                                index -= 1
                                                        elif emoji == "❌":
                                                            await msg.delete()
                                                            break
                                                        else:
                                                            index += 1
                                            if "?" in param:
                                                base = \
                                                    re.compile(r"([A-z]+)(\d*)?", re.DOTALL | re.IGNORECASE).findall(
                                                        name)[
                                                        0][0]
                                                similars = await self.get_similars(guild, base)
                                                file = random.choice(similars)
                                            if "e" in param:
                                                em = discord.Embed(color=em_color)
                                                em.set_image(url=file["url"])
                                                await channel.send(embed=em)
                                                continue
                                            if "u" in param:
                                                if file["path"]:
                                                    try:
                                                        await channel.send(files=[discord.File(file["path"])])
                                                    except:
                                                        logger.error(f"Impossible d'envoyer {name}", exc_info=True)
                                            if "w" in param:
                                                await channel.send(file["url"])
                                            if "!" in param:
                                                suppr = True

                                        async with channel.typing():
                                            if await self.config.guild(guild).SETTINGS.get_raw("antiflood"):
                                                ts = time.strftime("%H:%M", time.localtime())
                                                if ts not in self.cooldown:
                                                    self.cooldown = {ts: []}
                                                self.cooldown[ts].append(author.id)
                                                if self.cooldown[ts].count(author.id) > 3:
                                                    await channel.send("{} **Cooldown** • Patientez quelques secondes "
                                                                       "avant de poster d'autres fichiers...".format(author.mention))

                                            if file["path"]:
                                                try:
                                                    await channel.send(file=[discord.File(file["path"])])
                                                    continue
                                                except:
                                                    logger.error(f"Impossible d'envoyer {name}", exc_info=True)
                                            await channel.send(file["url"])

                                    elif name.lower() in ["list", "liste"]:
                                        async with channel.typing():
                                            txt = ""
                                            n = 1
                                            liste = sorted(await self.files_list(guild))
                                            for f in liste:
                                                base = re.compile(r"([A-z]+)(\d*)?", re.DOTALL | re.IGNORECASE).findall(f)[0][0]
                                                if f == base:
                                                    chunk = f":**{f}**:\n"
                                                else:
                                                    chunk = f"| :**{f}**:\n"
                                                if len(chunk) + len(txt) >= 1950:
                                                    em = discord.Embed(title=f"Fichiers disponibles sur {guild.name}",
                                                                       description=txt, color=em_color)
                                                    em.set_footer(text=f"Page #{n}")
                                                    try:
                                                        await author.send(embed=em)
                                                    except:
                                                        pass
                                                    txt = ""
                                                    n += 1
                                                txt += chunk
                                            em = discord.Embed(title=f"Fichiers disponibles sur {guild.name}",
                                                               description=txt, color=em_color)
                                            em.set_footer(text=f"Page #{n}")
                                            try:
                                                await author.send(embed=em)
                                            except:
                                                pass

    @commands.group()
    @checks.is_owner()
    async def pixellocal(self, ctx):
        """Paramètres de stockage de Pixel"""

    @pixellocal.command()
    async def filesize(self, ctx, value: float):
        """Change la taille maximale des fichiers (en B)"""
        if value > 1000:
            await self.config.FILE_MAX_SIZE.set(float(value))
            await ctx.send("**Taille maximale d'un fichier** • Réglé à {}".format(self.humanize_size(value)))
        else:
            await ctx.send("**Taille maximale d'un fichier** • Le minimum possible est 1 kB (1000 B)")

    @pixellocal.command()
    async def foldersize(self, ctx, value: float):
        """Change la taille maximale des dossiers des serveurs (en B)"""
        if value > 1000000:
            await self.config.FOLDER_MAX_SIZE.set(float(value))
            await ctx.send("**Taille maximale des dossiers serveurs** • Réglé à {}".format(self.humanize_size(value)))
        else:
            await ctx.send("**Taille maximale des dossiers serveurs** • Le minimum possible est 1 MB (1000000 B)")


    @commands.group(aliases=["pixset"])
    @commands.guild_only()
    @checks.admin_or_permissions(manage_messages=True)
    async def pixelset(self, ctx):
        """Commande centrale pour les paramètres de Pixel"""

    @pixelset.command()
    async def approb(self, ctx):
        """Active/Désactive l'approbation nécessaire des modérateurs du serveur pour ajouter un fichier"""
        guild = ctx.guild
        val = await self.config.guild(guild).SETTINGS.get_raw("need_approb")
        await self.config.guild(guild).SETTINGS.set_raw("need_approb", value=not val)
        if val:
            await ctx.send("**Approbation** • Proposer un fichier ne nécessitera plus l'approbation de la modération.")
        else:
            await ctx.send("**Approbation** • Proposer un fichier nécessitera désormais l'approbation de la modération.")

    @pixelset.command()
    async def antiflood(self, ctx):
        """Active/Désactive l'antiflood (3 fichiers / minute / membre)"""
        guild = ctx.guild
        val = await self.config.guild(guild).SETTINGS.get_raw("antiflood")
        await self.config.guild(guild).SETTINGS.set_raw("antiflood", value=not val)
        if val:
            await ctx.send("**Anti-flood** • La fonctionnalité est maintenant désactivée.")
        else:
            await ctx.send(
                "**Anti-flood** • La fonctionnalité est maintenant activée.")

    @pixelset.command(name="size")
    async def guildsize(self, ctx):
        """Affiche une liste des 10 fichiers les plus lourds et la place totale prise par le serveur"""
        guild = ctx.guild
        em_color = await ctx.embed_color()
        big = []
        liste = await self.files_list(guild)
        data = await self.config.guild(guild).FILES() + await self.config.guild(guild).WAITING()
        for f in liste:
            file = [i for i in data if i["name"] == f][0]
            if file["path"]:
                big.append((f, self._get_local_file_size(file["path"])))
        if big:
            big = sorted(big, key=operator.itemgetter(1), reverse=True)[:10]
            txt = ""
            for name, size in big:
                t = self.humanize_size(size)
                txt += f"**{name}** » {t}\n"
            if txt:
                em = discord.Embed(title="10 fichiers les plus lourds stockés localement", description=txt, color=em_color)
                em.set_footer(text="Total occupé par ce serveur = {} / {} disponibles".format(
                    self.humanize_size(self._get_folder_size(await self.guild_path(guild))),
                    self.humanize_size(await self.config.FOLDER_MAX_SIZE())))
                await ctx.send(embed=em)
            else:
                await ctx.send("**Aucune donnée à afficher** » Il semblerait qu'aucun fichier "
                               "ne soit stocké localement pour le moment.")
        else:
            await ctx.send("**Aucune donnée à afficher** » Il semblerait qu'aucun fichier "
                           "ne soit stocké localement pour le moment.")

    @pixelset.group()
    @checks.admin_or_permissions(ban_members=True)
    async def userblacklist(self, ctx):
        """Blacklister un membre du serveur"""

    @userblacklist.command(name="add")
    async def black_add_user(self, ctx, user: discord.Member):
        """Ajouter un membre à la blacklist Pixel"""
        guild = ctx.guild
        liste = await self.config.guild(guild).SETTINGS.get_raw("users_blacklist")
        if user.id not in liste:
            liste.append(user.id)
            await self.config.guild(guild).SETTINGS.set_raw("users_blacklist", value=liste)
            await ctx.send("**Blacklist de membres** • *{}* ajouté.".format(user.name))
        else:
            await ctx.send("**Blacklist de membres** • *{}* déjà présent dans la blacklist.".format(user.name))

    @userblacklist.command(name="remove")
    async def black_remove_user(self, ctx, user: discord.Member):
        """Retirer un membre de la blacklist Pixel"""
        guild = ctx.guild
        liste = await self.config.guild(guild).SETTINGS.get_raw("users_blacklist")
        if user.id in liste:
            liste.remove(user.id)
            await self.config.guild(guild).SETTINGS.set_raw("users_blacklist", value=liste)
            await ctx.send("**Blacklist de membres** • *{}* retiré.".format(user.name))
        else:
            await ctx.send("**Blacklist de membres** • *{}* n'est pas présent dans la blacklist.".format(user.name))

    @pixelset.group()
    @checks.admin_or_permissions(ban_members=True)
    async def channelblacklist(self, ctx):
        """Blacklister un channel du serveur"""

    @channelblacklist.command(name="add")
    async def black_add_channel(self, ctx, channel: discord.TextChannel):
        """Ajouter un channel à la blacklist Pixel"""
        guild = ctx.guild
        liste = await self.config.guild(guild).SETTINGS.get_raw("channels_blacklist")
        if channel.id not in liste:
            liste.append(channel.id)
            await self.config.guild(guild).SETTINGS.set_raw("channels_blacklist", value=liste)
            await ctx.send("**Blacklist de salons** • *{}* ajouté.".format(channel.name))
        else:
            await ctx.send("**Blacklist de salons** • *{}* déjà présent dans la blacklist.".format(channel.name))

    @channelblacklist.command(name="remove")
    async def black_remove_channel(self, ctx, channel: discord.TextChannel):
        """Ajouter un channel à la blacklist Pixel"""
        guild = ctx.guild
        liste = await self.config.guild(guild).SETTINGS.get_raw("channels_blacklist")
        if channel.id in liste:
            liste.remove(channel.id)
            await self.config.guild(guild).SETTINGS.set_raw("channels_blacklist", value=liste)
            await ctx.send("**Blacklist de salons** • *{}* retiré.".format(channel.name))
        else:
            await ctx.send("**Blacklist de salons** • *{}* n'est pas présent dans la blacklist.".format(channel.name))

