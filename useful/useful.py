import logging
import re
from urllib.request import urlopen

import discord
import instaloader
import wikipedia
import wikipediaapi
from bs4 import BeautifulSoup
from redbot.core import commands, Config, checks

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
        self.cache = {"_instagram": {}, "instaload": False}


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

    def load_instagram_post(self, code: str):
        if not self.instaload.test_login():
            if not self.cache["instaload"]:
                self.instaload.login(self.config.INSTALOADER_LOGIN, self.config.INSTALOADER_PASSWORD)
                self.instaload.save_session_to_file()
                self.cache["instaload"] = True
            else:
                self.instaload.load_session_from_file(self.config.INSTALOADER_LOGIN)

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
                    async with message.channel.typing():
                        code = r[0]
                        post, images, videos = self.load_instagram_post(code)
                        medias = images[1:] + videos
                        if medias:
                            logger.info("Post instagram détecté avec médias à afficher")
                            if len(medias) > 1 or videos:
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
                    if message.guild.permissions_for(user).manage_messages or user == message.author:
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
                                        em = discord.Embed(color=message.author.color, timestamp=post.date_utc)
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