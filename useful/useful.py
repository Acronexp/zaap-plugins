import re
from urllib.request import urlopen

import discord
import wikipedia
import wikipediaapi
from bs4 import BeautifulSoup
from redbot.core import commands


class Useful(commands.Cog):
    """Commandes qui peuvent être utiles"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

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
                resum += "\n\n[En savoir plus...]({})".format(p.fullurl)
                em = discord.Embed(title=r.capitalize(), description=resum, color=0xeeeeee)
                em.set_thumbnail(url=image)
                em.set_footer(text="Similaire: {}".format(", ".join(s[0])))
                return em
            else:
                if langue == "en":
                    return "Impossible de trouver {}".format(recherche)
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
            await ctx.send("**Inaccessible** • Le numéro est incorrect ou la page est inaccessible")
