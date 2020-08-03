import logging
import os
import re
import time
from urllib.parse import urlsplit

import aiofiles
import aiohttp
import discord
import requests
from redbot.core import Config, checks, commands
from redbot.core.data_manager import cog_data_path

__version__ = "1.0.0"
__need__ = ["aiofiles"]

logger = logging.getLogger("red.economy")

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
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        default_global = {"FOLDER_MAX_SIZE": 2e8, # 200 MB / serveur
                          "FILE_MAX_SIZE": 1e7, # 10 MB / fichier
                          "AUTHORISED_TYPES": ["image", "video", "audio"]}
        default_guild = {"SETTINGS": {"need_approb": True},
                         "WAITING": {},
                         "FILES": {}}
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)


    async def waiting_list(self, guild: discord.Guild):
        data = await self.config.guild(guild).WAITING()
        return list(data.keys())

    async def files_list(self, guild: discord.Guild):
        data = await self.config.guild(guild).FILES()
        return list(data.keys())

    def _get_folder_size(self, path):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return int(total_size)

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

    async def download_file(self, source_url, guild: discord.Guild, name = None):
        """Télécharger un fichier depuis une URL

        source_url = URL depuis lequel le fichier doit être téléchargé (doit terminer par son extension)
        guild = Serveur à l'origine de la demande (pour le rangement)
        name = Nom à donner au fichier"""
        name = name.lower()
        ext = os.path.splitext(os.path.basename(urlsplit(source_url).path))[1]
        guild_path = cog_data_path(self) / f"files/{guild.id}/"
        if not guild_path.exists():
            guild_path.mkdir(parents=True)

        if ext.lower() in [".jpeg", ".jpg", ".png", ".gif", ".mp3", ".wav", ".mp4", ".webm"]:
            file = name + ext
            file_path = cog_data_path(self) / f"files/{guild.id}/{file}"
            n = 1
            while file_path.exists():
                file_path = cog_data_path(self) / f"files/{guild.id}/{file}{n}"
                n += 1

            if self._get_file_type(source_url) in await self.config.AUTHORISED_TYPES():
                if self._get_file_length(source_url) > await self.config.FILE_MAX_SIZE():
                    if self._get_file_length(source_url) + self._get_folder_size(str(
                            guild_path)) > await self.config.FOLDER_MAX_SIZE():

                        async with aiohttp.ClientSession() as session:
                            async with session.get(source_url) as resp:
                                if resp.status == 200:
                                    f = await aiofiles.open(str(file_path), mode='wb')
                                    await f.write(await resp.read())
                                    await f.close()
                                    return file_path
                                else:
                                    raise DownloadError("Impossible de télécharger le fichier demandé")
                    else:
                        raise MaxFolderSize("Le poids du dossier du serveur est déjà trop important")
                else:
                    raise MaxFileSize("Le poids du fichier dépasse le maximum imposé par le propriétaire")
        raise ExtensionNotSupported("L'extension donnée n'est pas supportée")

    def any_num(self, s):
        return any(i.isdigit() for i in s)

    @commands.group(aliases=["pix"])
    @checks.mod_or_permissions(administrator=True)
    async def pixel(self, ctx):
        """Gestion des fichiers personnalisés du serveur"""

    @pixel.command(name="add")
    async def pixel_add(self, ctx, name, url = None):
        """Ajouter ou proposer un fichier personnalisé (image, audio ou vidéo)

        __Types supportés :__ jpeg, jpg, png, gif, mp3, wav, mp4 et webm
        Si aucune URL n'est donnée, prendra le fichier importé sur Discord avec la commande"""
        author, guild = ctx.author, ctx.guild
        name = name.lower()
        complete = name
        if self.any_num(name):
            name, num = re.compile(r"^(.*?)(\d+)$", re.DOTALL | re.IGNORECASE).findall(name)

        if ":" not in complete:
            await ctx.send("**Erreur** • Ne mettez pas `:` dans le nom de votre fichier !")
            return
        if complete not in ["list", "liste"]:
            await ctx.send("**Réservé** • Le nom que vous voulez utiliser est réservé car utilisé pour des "
                           "fonctionnalités spécifiques")

        if complete not in await self.waiting_list(guild):
            if complete not in await self.files_list(guild):
                if not url:
                    attachs = ctx.message.attachments
                    if not attachs:
                        await ctx.send("**Aucun fichier fourni** • Fournissez une URL du fichier ou téléchargez-le "
                                       "directement sur Discord avec la commande")
                        return
                    elif len(attachs) > 1:
                        await ctx.send("**Plusieurs fichiers fournis** • Vous ne pouvez ajouter qu'un seul fichier à la fois")
                        return

                    attach = attachs[0]
                    try:
                        filepath = await self.download_file(attach.url, guild, complete)
                    except ExtensionNotSupported:
                        await ctx.send("**Extension non supportée** • L'extension du fichier doit figurer dans la liste fournie dans `;help pixel add`")
                        return
                    except MaxFileSize:
                        await ctx.send("**Fichier trop lourd** • Le fichier dépasse la taille limite imposée de {}B".format(await self.config.MAX_FILE_SIZE()))
                        return
                    except MaxFolderSize:
                        await ctx.send("**Dossier trop lourd** • Videz le dossier du serveur avant de rajouter d'autres"
                                       " fichiers, il a atteint la taille maximale de {}B".format(await self.config.MAX_FOLDER_SIZE()))
                        return
                    except DownloadError:
                        await ctx.send("**Erreur** • Le fichier n'a pas pu être téléchargé pour une raison inconnue. "
                                       "Essayez de l'héberger sur *imgur* par exemple et réessayez.")
                        return

                    if await self.config.guild(guild).SETTINGS.get_raw("need_approb"):
                        if guild.permissions_for(author).manage_messages or guild.permissions_for(author).administrator:
                            file = {"path": filepath,
                                    "author": author.id,
                                    "url": attach.url,
                                    "added_on": time.time(),
                                    "used_count": 0}

