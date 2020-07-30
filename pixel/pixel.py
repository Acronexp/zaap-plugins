import asyncio
import os
import random
import re
import time
from collections import namedtuple
from copy import deepcopy
from urllib import request
import requests
import aiofiles
import string
import aiohttp
import discord

from redbot.core import Config, checks, commands
from redbot.core.data_manager import cog_data_path

__version__ = "1.0.0"

class PixelFile:
    """Représente un fichier Pixel"""
    def __init__(self, cog, guild: discord.Guild, id: str):
        self.cog = cog
        self.guild = guild
        self.file = self.cog.get_post(self, write=True)

    def __str__(self):
        return self.post["name"]

    def __int__(self):
        return self.cog.find_post_id(self.server, self.post["name"])


class Pixel(commands.Cog):
    """Stockage de stickers personnalisés"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        default_global = {"FOLDER_MAX_SIZE": 2e8, # 200 MB / serveur
                          "FILE_MAX_SIZE": 1e7, # 10 MB / fichier
                          "AUTHORISED_TYPES": ["image", "video", "audio"]}
        default_guild = {"SETTINGS": {},
                         "FILES": {}}
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.folderspath = cog_data_path(self) / f"files/"

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
        guild = Serveur à l'origine de la demande
        name = Nom à donner au fichier"""
        name = name.lower()
        file_name = source_url.split("/")[-1]
        file_ext = file_name.split(".")[-1]

        file = name + "." + file_ext
        file_path = cog_data_path(self) / f"files/{guild.id}/{file}"
        if not file_path.exists():
            if self._get_file_type(source_url) in self.config.AUTHORISED_TYPES():
                if self._get_file_length(source_url) > self.config.FILE_MAX_SIZE():
                    if self._get_file_length(source_url) + self._get_folder_size(
                            str(cog_data_path(self) / f"files/{guild.id}")) > self.config.FOLDER_MAX_SIZE():
                        async with aiohttp.ClientSession() as session:
                            async with session.get(source_url) as resp:
                                if resp.status == 200:
                                    f = await aiofiles.open(str(file_path), mode='wb')
                                    await f.write(await resp.read())
                                    await f.close()
                                    return file_path
        return None


    @commands.group(aliases=["pix"])
    @checks.mod_or_permissions(administrator=True)
    async def pixel(self, ctx):
        """Gestion des fichiers personnalisés du serveur"""

    @pixel.command(name="add")
    async def pixel_add(self, ctx, name, url = None):
        """Ajouter un fichier personnalisé (image, audio ou vidéo)

        __Types supportés :__ jpeg, jpg, png, gif, mp3, wav, mp4 et webm
        Si aucune URL n'est donnée, prendra le fichier importé sur Discord avec la commande"""
