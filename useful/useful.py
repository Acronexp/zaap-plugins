import asyncio
import logging
import os
import re
from datetime import datetime
from urllib.request import urlopen

import discord
import instaloader
import wikipedia
import wikipediaapi
from bs4 import BeautifulSoup
from redbot.core import commands, Config, checks
from redbot.core.data_manager import cog_data_path

logger = logging.getLogger("red.zaap-plugins.useful")

class Useful(commands.Cog):
    """Commandes qui peuvent être utiles"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        default_global = {"INSTALOADER_LOGIN": "",
                          "INSTALOADER_PASSWORD": ""}
        self.config.register_global(**default_global)

        self.instaload = instaloader.Instaloader()
        self.cache = {"_instagram": {}, "instaload": False, "tales": {}}

        self.temp = cog_data_path(self) / "temp"
        self.temp.mkdir(exist_ok=True, parents=True)


    def redux(self, string: str, separateur: str = ".", limite: int = 2000):
        n = -1
        while len(separateur.join(string.split(separateur)[:n])) >= limite:
            n -= 1
        return separateur.join(string.split(separateur)[:n]) + separateur

    def wiki(self, recherche: str, langue: str = 'fr', souple: bool = True):
        wikipedia.set_lang(langue)
        wikiplus = wikipediaapi.Wikipedia(langue)
        s = wikipedia.search(recherche, 8, True)
        try:
            if s[1]:
                r = s[1]
            else:
                r = s[0][0] if s[0] else None
            if r:
                page = wikipedia.page(r, auto_suggest=souple)
                images = page.images
                image = images[0]
                for i in images:
                    if i.endswith(".png") or i.endswith(".gif") or i.endswith(".jpg") or i.endswith(".jpeg"):
                        image = i
                resum = page.summary
                if not resum:
                    resum = "Contenu indisponible"
                if len(resum) + len(r) > 1995:
                    resum = self.redux(resum, limite=1960)
                p = wikiplus.page(r)
                resum += "\n[En savoir plus...]({})".format(p.fullurl)
                em = discord.Embed(title=r.capitalize(), description=resum, color=0xeeeeee)
                em.set_thumbnail(url=image)
                em.set_footer(text="Voir aussi · {}".format(", ".join(s[0][1:])))
                return em
            else:
                if langue == "en":
                    return "Impossible de trouver *{}*".format(recherche)
                else:
                    return self.wiki(recherche, "en")
        except:
            if langue == "en":
                if souple:
                    if s[0]:
                        if len(s[0]) >= 2:
                            wikipedia.set_lang("fr")
                            s = wikipedia.search(recherche, 3, True)
                            return "**Introuvable** • Réessayez peut-être avec *{}* ?".format(s[0][1])
                        else:
                            return "**Introuvable** • Aucun résultat pour *{}*".format(recherche)
                    else:
                        return "**Introuvable** • Aucun résultat pour *{}*".format(recherche)
                else:
                    return self.wiki(recherche, "en", False)
            else:
                if souple:
                    return self.wiki(recherche, "en")
                else:
                    return self.wiki(recherche, "fr", False)

    @commands.command(name="wikipedia", aliases=["wiki"])
    async def wiki_search(self, ctx, *search):
        """Recherche sur Wikipedia (FR si dispo. sinon EN)"""
        search = " ".join(search)
        async with ctx.channel.typing():
            result = self.wiki(search)
        if result:
            if type(result) is str:
                await ctx.send(result)
            else:
                await ctx.send(embed=result)
        else:
            await ctx.send("**Erreur** • Aucun résultat ne peut être affiché")


    def extract_scp(self, url: str):
        html = urlopen(url).read()
        soup = BeautifulSoup(html, "html")
        for script in soup(["script", "style"]):
            script.extract()
        div = soup.find("div", {"id": "page-content"})
        texts = []
        for x in div.findAll('p'):
            txt = x.text.replace("\\'", "'")
            reformat = re.compile(r"(Item #:|Object Class:|Special Containment Procedures:|Description:)",
                                  re.DOTALL | re.IGNORECASE).findall(txt)
            if reformat:
                base = reformat[0]
                txt = txt.replace(base, f"**{base}**")
            texts.append(txt)
        return texts

    @commands.command(name="scp")
    async def scp_search(self, ctx, num: int):
        """Recherche dans la base de données de la Fondation SCP (EN)"""
        if 1 <= num <= 5999:
            link = "http://www.scp-wiki.net/scp-{:03}".format(num)
            async with ctx.channel.typing():
                text = self.extract_scp(link)
            if text:
                texte = "\n".join(text)
                if len(texte) > 1950:
                    texte = self.redux(texte, limite=1950)
                texte += "\n\n[Consulter le dossier...]({})".format(link)
                em = discord.Embed(description=texte, color=0x653C3C)
                em.set_footer(text="SCP Foundation", icon_url="https://i.imgur.com/UKR9LxY.png?1")
                await ctx.send(embed=em)
            else:
                await ctx.send("**Inaccessible** • Le nombre est incorrect ou la page est inaccessible")
        else:
            await ctx.send("**Inaccessible** • Les SCP ne vont pour l'instant que de 1 à 5999.")

    async def load_instagram_post(self, code: str):
        if not self.instaload.test_login():
            if not self.cache["instaload"]:
                self.instaload.login(await self.config.INSTALOADER_LOGIN(), await self.config.INSTALOADER_PASSWORD())
                self.instaload.save_session_to_file()
                self.cache["instaload"] = True
            else:
                self.instaload.load_session_from_file(await self.config.INSTALOADER_LOGIN())

        post = instaloader.Post.from_shortcode(self.instaload.context, code)
        images, videos = [], []
        if post.typename == "GraphSidecar":
            nodes = post.get_sidecar_nodes()
            for node in nodes:
                if node.is_video:
                    videos.append(node.video_url)
                else:
                    images.append(node.display_url)
        elif post.typename == "GraphVideo":
            videos.append(post.video_url)
        else:
            images.append(post.url)
        return post, images, videos

    @commands.command()
    @checks.is_owner()
    async def instaloaderapi(self, ctx, username: str = "", password: str = ""):
        """Modifie le compte instagram utilisé pour donner les previews"""
        tb = ""
        if username:
            tb += "Login ajouté\n"
        else:
            tb += "Login réinitialisé\n"
        if password:
            tb += "Mot de passe ajouté\n"
        else:
            tb += "Mot de passe retiré\n"
        await self.config.INSTALOADER_LOGIN.set(username)
        await self.config.INSTALOADER_PASSWORD.set(password)
        await ctx.send(tb)

    @commands.group(name="tale")
    @commands.guild_only()
    async def _tale(self, ctx):
        """Enregistrer une suite de messages sur un fichier .txt"""

    @_tale.command()
    async def now(self, ctx, teller: discord.Member = None, channel: discord.TextChannel = None):
        """Enregistre les messages d'un membre sur un salon à partir de maintenant

        Pour arrêter, le raconteur doit dire "stop" (sans rien d'autre)
        - Si le <teller> n'est pas spécifié, c'est celui qui fait la commande qui l'est
        - Si le salon n'est pas spécifié, c'est celui où est réalisé la commande"""
        if not teller: teller = ctx.author
        if not channel: channel = ctx.channel
        em_color = await ctx.embed_color()

        path = str(self.temp)
        filepath = path + "/{1}_{0}.txt".format(teller.name, datetime.now().strftime("%Y%m%d%H%M"))
        nb = 0
        pre_txt = "| Auteur = {}\n" \
              "| Salon = {}\n" \
              "| Date de début = {}\n\n".format(str(teller), channel.name, datetime.now().strftime("%d/%m/%Y %H:%M"))
        txt = ""

        def check(m: discord.Message):
            return m.author == teller and m.channel == channel

        async def write(txt: str):
            file = open(filepath, "w")
            file.write(txt)
            file.close()
            return file

        async def post_all(txt: str):
            chunks = txt.split("\n")
            page = 1
            post = pre_txt
            for chunk in chunks:
                if len(chunk) + len(post) < 1950:
                    post += chunk + "\n"
                else:
                    em = discord.Embed(description=post, color=em_color)
                    em.set_footer(text=f"Page #{page}")
                    await channel.send(embed=em)
                    post = chunk + "\n"
                    page += 1
            if post:
                em = discord.Embed(description=post, color=em_color)
                em.set_footer(text=f"Page #{page}")
                await channel.send(embed=em)

        while True:
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=300)
            except asyncio.TimeoutError:
                em = discord.Embed(description="🔴 **Fin auto. de l'enregistrement**\n"
                                               "Aucun message n'a été écrit depuis 5 min.", color=em_color)
                em.set_footer(text="Veuillez patienter...")
                info = await channel.send(embed=em)
                try:
                    async with channel.typing():
                        await post_all(txt)
                        await write(pre_txt + txt)
                    await channel.send(files=[discord.File(filepath)])
                    os.remove(filepath)
                except:
                    await channel.send("**Erreur** • Je n'ai pas réussi à upload le fichier...")
                await info.delete()
            else:
                if msg.content:
                    if msg.content.lower() == "stop":
                        em = discord.Embed(description="🔴 **Fin de l'enregistrement par l'auteur**\n"
                                                       "Il y a eu {} messages enregistrés.".format(nb), color=em_color)
                        em.set_footer(text="Veuillez patienter...")
                        info = await channel.send(embed=em)
                        try:
                            async with channel.typing():
                                await post_all(txt)
                                await write(pre_txt + txt)
                            await channel.send(files=[discord.File(filepath)])
                            os.remove(filepath)
                        except:
                            await channel.send("**Erreur** • Je n'ai pas réussi à upload le fichier...")
                        await info.delete()
                    else:
                        txt += msg.content + "\n"
                        nb += 1


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild:
            if "<" or ">" in message.content:
                message.content = message.content.replace("<", "")
                message.content = message.content.replace(">", "")
            if "https://www.instagram.com/p/" in message.content:
                r = re.compile(r'(?<!!)https://www\.instagram\.com/p/([\w\-]+).*?', re.DOTALL | re.IGNORECASE).findall(
                    message.content)
                if r:
                    code = r[0]
                    post, images, videos = await self.load_instagram_post(code)
                    medias = images[1:] + videos
                    if medias:
                        logger.info("Post instagram détecté avec médias à afficher")
                        if len(medias) > 0 or videos:
                            profile = post.owner_profile
                            previews = medias
                            n = 1
                            for media in medias:
                                if media in videos:
                                    txt = "Preview +{}/{} · {}\n".format(
                                        n, len(medias), post.date_utc.strftime("Publié le %d/%m/%Y à %H:%M")) + media
                                    await message.channel.send(txt)
                                    n += 1
                                    previews.remove(media)

                            if previews:
                                self.cache["_instagram"][message.id] = {"previews": previews,
                                                                        "images": images,
                                                                        "videos": videos,
                                                                        "nb": n,
                                                                        "total": len(medias),
                                                                        "post": post,
                                                                        "profile": profile,
                                                                        "message": message,
                                                                        "posted": False}
                                await message.add_reaction("👁")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        message = reaction.message
        channel = message.channel
        if message.guild:
            if reaction.emoji == "👁":
                if not user.bot:
                    if user.permissions_in(channel).manage_messages or user == message.author:
                        if message.id in self.cache["_instagram"]:
                            if not self.cache["_instagram"][message.id]["posted"]:
                                cache = self.cache["_instagram"][message.id]
                                post, profile = cache["post"], cache["profile"]
                                images, videos = cache["images"], cache["videos"]
                                n = cache["nb"]
                                total = cache["total"]
                                medias = cache["previews"]
                                async with channel.typing():
                                    for media in medias:
                                        em = discord.Embed(color=0xce0072, timestamp=post.date_utc)
                                        if n == 1:
                                            short_url = "https://www.instagram.com/p/" + post.shortcode
                                            em.set_author(name="{} (@{})".format(profile.full_name, profile.username),
                                                          url=short_url)
                                        if media in images:
                                            em.set_image(url=media)
                                            em.set_footer(text="Preview +{}/{}".format(n, total))
                                            await channel.send(embed=em)
                                        else:
                                            txt = "Preview +{}/{} · {}\n".format(
                                                n, total, post.date_utc.strftime("Publié le %d/%m/%Y à %H:%M")) + media
                                            await channel.send(txt)
                                        n += 1
                                    self.cache["_instagram"][message.id]["posted"] = True
                                    try:
                                        await message.remove_reaction("👁", user)
                                    except:
                                        pass