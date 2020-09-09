import logging
import os
from collections import namedtuple

import discord
from redbot.core import Config, checks, commands
from redbot.core.data_manager import cog_data_path

logger = logging.getLogger("red.zaap-plugins.humanity")

_Palette = namedtuple("colors", ["white", "black", "cyan", "yellow", "magenta"])
Palette = _Palette(0xFAFAFA, 0x17202A, 0x4DD0E1, 0xFFEB3B, 0xEC407A)

DEFAULT_MODE = "original"

class Humanity(commands.Cog):
    """Basiquement Cards Against Humanity mais en mieux"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.path = cog_data_path(self) / "packs"
        self.path.mkdir(exist_ok=True, parents=True)
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)

        default_guild = {"default_mode": DEFAULT_MODE,
                         "original_win": 5,
                         "plus_win": 5,
                         "course_start": 5,
                         "packs": []}
        self.config.register_guild(**default_guild)
        self.packs = {}
        self.load_packs()

    def filespaths(self, directory):
        for dirpath, _, filenames in os.walk(directory):
            for f in filenames:
                if f.endswith(".txt"):
                    yield os.path.abspath(os.path.join(dirpath, f))

    def load_packs(self):
        self.packs = {}
        nb = 0
        strnum = lambda n: f"pack_{n}"
        for path in self.filespaths(self.path):
            with open(path, 'r') as file:
                pack = {"excl": None}
                pack_id = strnum(nb)
                pack["cards"] = {"black": [],
                                 "white": [],
                                 "yellow": []}
                for line in file:
                    if "--" in line:
                        if line.startswith("ID"):
                            pack_id = line.split("--")[1].strip().lower()
                        elif line.startswith("NAME"):
                            pack["name"] = line.split("--")[1].strip()
                        elif line.startswith("DESC"):
                            pack["desc"] = line.split("--")[1].strip()
                        elif line.startswith("LANG"):
                            lang = line.split("--")[1].strip()
                            if len(lang) == 2:
                                pack["lang"] = lang
                            else:
                                break
                        elif line.startswith("EXCL"):
                            id_string = line.split("--")[1].strip()
                            try:
                                ids = [int(i.strip()) for i in id_string.split(";")]
                                pack["excl"] = ids
                            except:
                                break

                        elif line.startswith("B--"):
                            card = line.split("--")[1].strip()
                            if 1 <= card.count("{}") <= 3:
                                pack["cards"]["black"].append(card)
                        elif line.startswith("W--"):
                            pack["cards"]["white"].append(line.split("--")[1].strip())
                        elif line.startswith("Y--"):
                            card = line.split("--")[1].strip()
                            try:
                                mots = (i.lower().strip() for i in card.split(";"))
                                pack["cards"]["yellow"].append(mots)
                            except:
                                continue
                        else:
                            pass # On ignore tout le reste, que ce soit lignes blanches ou lignes invalides
                    else:
                        pass
                self.packs[pack_id] = pack
                nb += 1
        return self.packs

    @commands.group(name="humanity", aliases=["cah"])
    @commands.guild_only()
    async def _humanity(self, ctx):
        """Jouer à Cards Against Humanity"""


    @_humanity.group(name="set")
    async def _humanity_set(self, ctx):
        """Options de partie"""

    @_humanity_set.command(name="default")
    @checks.admin_or_permissions(manage_messages=True)
    async def default_mode(self, ctx, mode: str = DEFAULT_MODE):
        """Modifie le mode par défaut (utilisé si non précisé lors du démarrage de la partie)"""
        mode = mode.lower()
        if mode in ["original", "plus", "course"]:
            await self.config.guild(ctx.guild).default_mode.set(mode)
            await ctx.send(
                f"**Mode par défaut modifié** • Le mode {mode} se lancera si aucun mode n'est spécifié lors du démarrage d'une partie.")
        else:
            await ctx.send(
                f"**Erreur** • Le mode '{mode}' n'existe pas. Choisissez entre `original`, `plus` et `course`.")


    @_humanity.group(name="packs")
    async def _humanity_packs(self, ctx):
        """Gestion des packs de cartes"""

    @_humanity_packs.command()
    async def add(self, ctx, pack_id: str):
        """Ajoute un pack de cartes à utiliser"""
        liste = self.packs
        if pack_id.lower() in liste:
            pack = liste[pack_id.lower()]
            if pack["excl"]:
                if ctx.guild.id not in pack["excl"]:
                    await ctx.send(
                        f"**Exclusivité non respectée** • Le pack {pack_id} est exclusif à un serveur et ne peut être utilisé ici.")
                    return
            packs = await self.config.guild(ctx.guild).packs()
            if pack_id.lower() not in packs:
                packs.append(pack_id.lower())
                await self.config.guild(ctx.guild).packs.set(packs)
                await ctx.send(f"**Pack ajouté** • Le pack {pack_id} sera chargé aux prochaines parties (s'il est compatible avec le mode utilisé).")
            else:
                await ctx.send(
                    f"**Déjà utilisé** • Vous utilisez déjà ce pack dans vos parties."
                )
        else:
            await ctx.send(
                f"**Pack inconnu** • Le pack {pack_id} ne semble pas exister. Consultez la liste avec `;cah packs list`.")

    @_humanity_packs.command()
    async def remove(self, ctx, pack_id: str):
        """Retire un pack de cartes à utiliser"""
        liste = self.packs
        if pack_id.lower() in liste:
            packs = await self.config.guild(ctx.guild).packs()
            if pack_id.lower() in packs:
                packs.remove(pack_id.lower())
                await self.config.guild(ctx.guild).packs.set(packs)
                await ctx.send(
                    f"**Pack retiré** • Le pack {pack_id} ne sera plus chargé.")
            else:
                await ctx.send(
                    f"**Non présent** • Le pack {pack_id} n'était pas dans la liste de packs à utiliser.")
        else:
            await ctx.send(
                f"**Pack inconnu** • Le pack {pack_id} n'existe pas. Consultez la liste avec `;cah packs list`.")

    @_humanity_packs.command()
    async def list(self, ctx):
        """Consulter la liste des packs disponibles

        Pour proposer un pack de cartes, contactez Acrone#4424"""
        color = await self.bot.get_embed_color(ctx.channel)
        em = discord.Embed(color=color)
        for p in self.packs:
            pack = self.packs[p]
            if pack["excl"]:
                if ctx.guild.id not in pack["excl"]:
                    continue
            total = sum([len(pack["cards"]["white"]), len(pack["cards"]["black"]), len(pack["cards"]["yellow"])])
            txt = "**Description** · {}\n" \
                  "**Langue** · {}\n" \
                  "**Contenu** · {} cartes dont :\n" \
                  "   - {} noires\n" \
                  "   - {} blanches\n" \
                  "   - {} jaunes\n".format(pack["desc"], pack["lang"], total, len(pack["cards"]["black"]),
                                            len(pack["cards"]["white"]), len(pack["cards"]["yellow"]))
            em.add_field(name="{} (ID:{})".format(pack["name"], p), value=txt, inline=False)
        await ctx.send(embed=em)

    @_humanity.command(aliases=["regles"])
    async def rules(self, ctx):
        """Affiche les règles des différents modes"""
        original = "*Mode classique directement tiré du jeu de cartes Cards Against Humanity*\n" \
                   "A chaque tour, un maître (désigné par le bot, chaque joueur l'étant tour à tour) pioche une carte noire au hasard. " \
                   "Les cartes noires possèdent des espaces vides (représentés par ❔) que les élèves (autre joueurs) doivent remplir avec des cartes blanches." \
                   " Ces cartes blanches sont des morceaux de phrases, voire simplement un unique mot, prédéfinies en avance qui permettent justement de combler les espaces vides. " \
                   "Une fois que tout le monde a proposé sa carte, le maître va pouvoir choisir la combinaison de cartes (la noire avec la ou les blanche.s) qu'il préfère. Bien évidemment les propositions sont anonymes " \
                   "(réalisées en MP).\n" \
                   "Le joueur ayant remporté {} manches gagne la partie.".format(await self.config.guild(ctx.guild).original_win())
        em_original = discord.Embed(color=Palette.white, title="Règles • Original", description=original)

        plus = "*Mode exclusif à Zaap dérivé des règles officielles*\n" \
               "Ce mode fonctionne grossièrement comme le mode Original mais ajoute 3 cartes ayant des effets spéciaux :\n" \
               "- Si un joueur élève pioche une __carte jaune__ et qu'il décide de l'utiliser, il pourra donner la réponse qu'il désire pour remplir l'espace vide, " \
               "à ceci près qu'il doit obligatoirement glisser dans sa réponse le ou les mots-clefs présents sur la carte jaune.\n" \
               "- Si un joueur élève pioche une __carte magenta__ et qu'il décide de l'utiliser, il est totalement libre de la réponse qu'il donne (avec toutefois une restriction " \
               "sur la longueur de la réponse)\n" \
               "- Enfin, si un joueur maître pioche une __carte cyan__, le bot tire un échantillon de cartes noires dans lequel il peut piocher sa favorite. Ainsi la carte noire n'est pas imposée.\n" \
               "Le joueur ayant remporté {} manches gagne la partie.".format(await self.config.guild(ctx.guild).plus_win())
        em_plus = discord.Embed(color=Palette.cyan, title="Règles • Plus", description=plus)

        course = "*Mode exclusif à Zaap, dérivé des règles du mode Plus*\n" \
                 "Ce mode fonctionne comme le mode Plus mais est plus \"compétitif\" car comme au Uno, les joueurs partent avec un certain nombre de cartes ({}) et doivent s'en débarasser en premier. " \
                 "Cela signifie que lorsqu'un joueur élève voit sa carte blanche (ou jaune) choisie comme favorite du joueur maître, il ne repioche pas de carte. Il repioche une carte que si le round n'a pas été gagné." \
                 " En plus de cela :\n" \
                 "- Les cartes magenta ne sont pas disponibles\n" \
                 "- Le bot ne sélectionne que des cartes noires avec qu'un seul espace vide, de façon à ne se débarasser que d'une seule carte par round max\n" \
                 "- Si un joueur ne joue pas (temps de réponse écoulé) il doit piocher une carte supplémentaire\n" \
                 "Le joueur s'étant débarassé de toute ses cartes en premier gagne la partie.".format(await self.config.guild(ctx.guild).course_start())
        em_course = discord.Embed(color=Palette.yellow, title="Règles • Course", description=course)

        await ctx.send(embeds=[em_original, em_plus, em_course])


    @_humanity.command()
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def play(self, ctx, mode: str = None):
        """Démarrer ou rejoindre une partie de CAH

        **Modes de jeux :**
        `original` = Règles de base, issues du jeu Cards Against Humanity
        `plus` = Règles modifiées avec cartes spéciales

        Note : les différents modes utilisent les mêmes packs de cartes si ceux-ci sont compatibles"""
        guild = ctx.guild

        if not mode:
            mode = await self.config.guild(guild).default_mode()

