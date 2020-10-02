import logging
from datetime import datetime

import discord
import requests
from redbot.core import Config, commands

logger = logging.getLogger("red.zaap-plugins.extra")

class Extra(commands.Cog):
    """Outils utiles exploitant divers API publiques"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)

        default_guild = {}
        self.config.register_guild(**default_guild)

    def relink(self, link: str):
        """Raccourcissement de lien en utilisant rel.ink"""
        base = "https://rel.ink/"
        result = requests.post("https://rel.ink/api/links/", {"url": link})
        if result:
            return base + result.json()["hashid"]
        raise ConnectionError("Le lien n'a pu être créé")

    def create_qrcode(self, link: str, size: str = "200x200"):
        """Transformation de lien en QRCODE (si trop long, passe par relink automatiquement)"""
        if len(link) >= 500:
            link = self.relink(link)
        result = requests.get(f"https://api.qrserver.com/v1/create-qr-code/?data={link}&size={size}")
        if result:
            return result.url
        raise ConnectionError("Le QRcode n'a pu être créé")

    def read_qrcode(self, img: str):
        """Lecture de(s) QRCODE d'une image fournie en URL"""
        result = requests.get(f"https://api.qrserver.com/v1/read-qr-code/?fileurl={img}")
        if result:
            results = []
            for r in result.json():
                results.append(r["symbol"][0]["data"])
            return results
        raise ConnectionError("Aucun QRcode n'a pu être lu")

    def get_covid_status(self, country_code: str = None):
        """Renvoie le résumé quotidien de l'évolution du covid-19 dans le monde, ou dans un pays spécifié"""
        result = requests.get("https://api.covid19api.com/summary")
        if result:
            json = result.json()
            if country_code:
                for c in json["Countries"]:
                    if country_code.upper() == c["CountryCode"]:
                        return c
                else:
                    raise KeyError("Ce code pays n'existe pas")
            return json
        raise ConnectionError("Aucune info n'a été reçue depuis l'API")

    @commands.command(aliases=["relink"])
    async def shorten(self, ctx, lien: str):
        """Raccourcisseur d'URL"""
        notif = await ctx.send("Raccourcissement de votre URL en cours...")
        try:
            relink = self.relink(lien)
            await ctx.send("**Voici votre lien** » {}".format(relink))
        except:
            await ctx.send("**Erreur** • Impossible de créer votre URL")
        await notif.delete()

    @commands.command(aliases=["qrcode"])
    async def createqrcode(self, ctx, lien: str):
        """Transforme un lien en QRCODE"""
        notif = await ctx.send("Création du QRCODE en cours...")
        try:
            qrcode = self.create_qrcode(lien)
            await ctx.send("**Voici votre QRCODE** » {}".format(qrcode))
        except:
            await ctx.send("**Erreur** • Impossible de créer votre QRCODE")
        await notif.delete()

    @commands.command()
    async def readqrcode(self, ctx, img_url: str):
        """Tente de lire les QRCODE d'une image"""
        notif = await ctx.send("Patientez durant le scan de votre image... (peut être long si l'image est grande)")
        try:
            link = self.read_qrcode(img_url)
            await ctx.send("**Voici le contenu j'ai trouvé dans les QRCODE de votre image** » {}".format(", ".join(link)))
        except:
            await ctx.send("**Erreur** • Aucun QRCODE reconnu dans cette image")
        await notif.delete()

    @commands.command()
    async def covid(self, ctx, code_pays: str = None):
        """Affiche les stats d'un pays sur le Covid si le code du pays est précisé, sinon les stats globales (monde)"""
        if code_pays:
            code_pays = code_pays.upper()
            try:
                stats = self.get_covid_status(code_pays)
            except Exception as e:
                print(e)
                await ctx.send(f"**Erreur** • {e}")
                return
            desc = "**Cas confirmés** : {}\n".format(stats["TotalConfirmed"])
            desc += "**Morts** : {}\n".format(stats["TotalDeaths"])
            desc += "**Rétablis** : {}".format(stats["TotalRecovered"])
            em = discord.Embed(title="STATS COVID-19 • :flag_{}: {}".format(stats["CountryCode"].lower(), stats["Country"]),
                               description=desc,
                               color=await ctx.embed_color())
            today = "**Nouveaux cas confirmés** : {}\n".format(stats["NewConfirmed"])
            today += "**Morts** : {}\n".format(stats["NewDeaths"])
            today += "**Rétablis** : {}".format(stats["NewRecovered"])
            convert_date = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
            maj = convert_date(stats["Date"])
            em.timestamp = maj
            em.add_field(name="Dernière mise à jour", value=today)
            em.set_footer(text="Dernière MAJ")
            await ctx.send(embed=em)
        else:
            try:
                stats = self.get_covid_status()["Global"]
            except Exception as e:
                await ctx.send(f"**Erreur** • {e}")
                return
            desc = "**Cas confirmés** : {}\n".format(stats["TotalConfirmed"])
            desc += "**Morts** : {}\n".format(stats["TotalDeaths"])
            desc += "**Rétablis** : {}".format(stats["TotalRecovered"])
            em = discord.Embed(title="STATS COVID-19 • :earth_africa: Global",
                               description=desc,
                               color=await ctx.embed_color())
            today = "**Nouveaux cas confirmés** : {}\n".format(stats["NewConfirmed"])
            today += "**Morts** : {}\n".format(stats["NewDeaths"])
            today += "**Rétablis** : {}".format(stats["NewRecovered"])
            em.add_field(name="Dernière mise à jour", value=today)
            em.set_footer(text="Ces chiffres sont estimés à partir des rapports nationaux")
            await ctx.send(embed=em)
