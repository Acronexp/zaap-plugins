import asyncio
import logging
import os
import re
import subprocess
import time
from urllib.parse import urlsplit

import aiofiles
import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.data_manager import cog_data_path

logger = logging.getLogger("red.zaap-plugins.dank")

IMAGE_LINKS = re.compile(
    r"(https?:\/\/[^\"\'\s]*\.(?:png|jpg|jpeg|png)(\?size=[0-9]*)?)", flags=re.I
)

class Dank(commands.Cog):
    """Générateur de memes"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        self.temp = cog_data_path(self) / "temp"
        self.temp.mkdir(exist_ok=True, parents=True)

    async def search_for_images(self, ctx):
        urls = []
        async for message in ctx.channel.history(limit=10):
            if message.attachments:
                for attachment in message.attachments:
                    urls.append(attachment.url)
            match = IMAGE_LINKS.match(message.content)
            if match:
                urls.append(match.group(1))
        if not urls:
            return None
        else:
            return urls[0]

    async def download(self, url: str):
        seed = str(int(time.time()))
        file_name, ext = os.path.splitext(os.path.basename(urlsplit(url).path))
        filename = "{}_{}{}".format(seed, file_name, ext)
        filepath = "{}/{}".format(str(self.temp), filename)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        f = await aiofiles.open(str(filepath), mode='wb')
                        await f.write(await resp.read())
                        await f.close()
                    else:
                        raise ConnectionError()
            return filepath
        except Exception:
            logger.error("Error downloading", exc_info=True)
            return False

    @commands.command(aliases=["sm"])
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def simplememe(self, ctx, texte: str, url = None):
        """Ajoute du texte en haut d'une image pour en faire un meme"""
        if url is None:
            url = await self.search_for_images(ctx)
        if not url:
            return await ctx.send("**???** • Aucune image trouvée")
        async with ctx.typing():
            await ctx.send("Veuillez patienter...")
            f = await self.download(url)
            if not f:
                return await ctx.send("**Erreur** • Echec du téléchargement de l'image\n"
                                      "Avez-vous mis votre texte entre guillemets ? Si ce n'est pas le cas, le bot a simplement confondu votre texte avec une URL.")

            def make_meme(source, text: str):
                if os.path.exists(source):
                    text = text.replace("|", "\n")
                    name = time.strftime("%Y%m%d%H%M%S")
                    args = ['python', '-m', 'dankcli', source, text, '-f', name]
                    sub = subprocess.Popen(args, stdout=subprocess.PIPE, cwd=str(self.temp))
                    sub.wait()
                    if sub.returncode == 0:
                        path = self.temp / f"{name}.png"
                        if os.path.exists(str(path)):
                            return path
                raise OSError("Fichier introuvable")

            task = self.bot.loop.run_in_executor(None, make_meme, f, texte)
            try:
                path = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return await ctx.send("**Trop long** • Le processus a mis trop de temps à créer l'image")

            if not ctx.channel.permissions_for(ctx.me).send_messages:
                return
            if not ctx.channel.permissions_for(ctx.me).attach_files:
                await ctx.send("**Permissions manquantes** • Je ne peux pas envoyer de fichiers")
                return

            try:
                await ctx.send(file=discord.File(path))
            except:
                await ctx.send("**Erreur** • Je n'ai pas pu envoyer le fichier (prob. trop lourd)")

            os.remove(path)
            os.remove(f)
