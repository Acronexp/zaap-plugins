import asyncio
import logging
import operator
import random
import time

import discord
from fuzzywuzzy import process
from redbot.core import Config, commands, checks
from redbot.core.utils.menus import start_adding_reactions
from tabulate import tabulate

logger = logging.getLogger("red.zaap-plugins.october")

HALLOWEEN_COLOR = lambda: random.choice([0x5E32BA, 0xEB6123, 0x18181A, 0x96C457])

CANDIES = {
    "berlingot": {"name": "Berlingot", "ep": ["none", "rainbow"], "ew": [2, 1],
                  "img": ""},
    "marshmallow": {"name": "Marshmallow", "ep": ["none", "haunt", "ego"], "ew": [2, 2, 1],
                    "img": ""},
    "calisson": {"name": "Calisson", "ep": ["none", "fortune", "flip"], "ew": [2, 1, 2],
                 "img": ""},
    "caramel": {"name": "Caramel", "ep": ["haunt", "ego", "room"], "ew": [2, 2, 1],
                "img": ""},
    "chewinggum": {"name": "Chewing-gum", "ep": ["none", "room", "malus", "fortune"], "ew": [2, 1, 1, 1],
                   "img": ""},
    "dragee": {"name": "Dragée", "ep": ["none", "rainbow", "loss"], "ew": [2, 1, 2],
               "img": ""},
    "guimauve": {"name": "Guimauve", "ep": ["none", "loss", "fortune"], "ew": [1, 1, 1],
                 "img": ""},
    "reglisse": {"name": "Réglisse", "ep": ["malus", "flip", "rainbow"], "ew": [2, 2, 1],
                 "img": ""},
    "sucette": {"name": "Sucette", "ep": ["room", "ego", "haunt"], "ew": [2, 1, 2],
                "img": ""},
    "nougat": {"name": "Nougat", "ep": ["none", "rainbow", "flip"], "ew": [2, 2, 1],
               "img": ""}
}

ASTUCES = [
    "Votre score augmente d'autant de points que vous obtenez de bonbons",
    "Manger ou donner des bonbons ne fait pas baisser votre score, sauf si le bonbon contenait un effet 'malus'",
    "Certains bonbons déclenchent un effet lorsque vous le mangez, il peut être positif mais aussi négatif",
    "Il y a une dizaine d'effets qui peuvent être causés par les bonbons lorsqu'ils sont mangés",
    "Chaque bonbon a plus de chance de donner certains effets plutôt que d'autres",
    "Tous les bonbons ne peuvent pas donner tous les effets",
    "Il y a une limite de bonbons pouvant apparaître pendant un laps de temps donné",
    "Il y a 2 types de spawn de bonbons : 'Au plus rapide' et 'Distribution générale'",
    "Ceci n'est pas une astuce",
    "Les bonbons virtuels ne donnent pas de caries",
    "Si vous mangez trop de bonbons, vous allez devenir e-diabétique",
    "Pour voir votre inventaire, votre score et les effets que vous subissez, faîtes ;poche",
    "Un top est disponible avec ;topevent",
    "Pour certaines commandes comme ';eat' vous pouvez noter vaguement le nom du bonbon, il sera reconnu automatiquement",
    "Des MAJ peuvent avoir lieues dans le mois pour modifier ou ajouter des choses, prenez garde !",
    "Vos bonbons n'ont pas de date limite de consommation",
    "Attention à l'abus de certains bonbons qui peuvent vous rendre malade : vous ne pourrez plus en manger pendant plusieurs minutes !"
]

BASE_DURATIONS = {
    "none": None,
    "flip": 300,
    "rainbow": 300,
    "haunt": 300,
    "fortune": None,
    "ego": 160,
    "loss": None,
    "malus": 600,
    "room": 600
}

EFFECT_TRAD_FR = {"dur_flip": "renversé",
                  "dur_rainbow": "arc-en-ciel",
                  "dur_haunt": "hanté",
                  "dur_ego": "égo",
                  "dur_malus": "malus",
                  "dur_room": "secret"}

class OctoberError(Exception):
    pass

class InvalidCandy(OctoberError):
    pass


class October(commands.Cog):
    """Event d'octobre 2020 (originellement pensé pour L'Appart)"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)

        default_member = {"score": 0,
                          "inv": {}}
        default_guild = {"spawn_counter_trigger": 100,
                         "spawn_cooldown": 180,
                         "spawn_channel": None,
                         "rainbow_roles": {"red": None,
                                           "orange": None,
                                           "yellow": None,
                                           "green": None,
                                           "blue": None,
                                           "purple": None},
                         "room_role": None}
        self.config.register_member(**default_member)
        self.config.register_guild(**default_guild)

        self.cache = {}
        self.status = {}

    def get_cache(self, guild: discord.Guild, reset: bool = False):
        if guild.id not in self.cache or reset:
            self.cache[guild.id] = {"spawn_counter": 0,
                                    "last_spawn": 0,

                                    "distrib_msg": None,
                                    "distrib_users": {},
                                    "distrib_candies": []}
        return self.cache[guild.id]

    def get_member_status(self, user: discord.Member, reset: bool = False):
        guild = user.guild
        if guild.id not in self.status:
            self.status[guild.id] = {}
        if user.id not in self.status[guild.id] or reset:
            self.status[guild.id][user.id] = {"dur_flip": 0,
                                              "dur_rainbow": 0,
                                              "dur_haunt": 0,
                                              "dur_ego": 0,
                                              "ego_cd": 0,
                                              "dur_malus": 0,
                                              "dur_room": 0}
        return self.status[guild.id][user.id]

    async def enough_candies(self, user: discord.Member, candy_id: str, need: int):
        """Vérifier la qté de bonbons de ce type possédés par le membre"""
        if candy_id in CANDIES and need >= 0:
            inv = await self.config.member(user).inv()
            if candy_id in inv:
                return need <= inv[candy_id]
            return False
        raise InvalidCandy("Il n'y a aucun bonbon à ce nom ou la quantité est invalide")

    async def add_candy(self, user: discord.Member, candy_id: str, qte: int):
        """Ajoute un bonbon au membre"""
        if candy_id in CANDIES and qte > 0:
            score, inv = await self.config.member(user).score(), await self.config.member(user).inv()
            score += qte
            if candy_id not in inv:
                inv[candy_id] = qte
            else:
                inv[candy_id] += qte
            await self.config.member(user).score.set(score)
            await self.config.member(user).inv.set(inv)
            return True
        raise InvalidCandy("Il n'y a aucun bonbon à ce nom ou la quantité est invalide")

    async def remove_candy(self, user: discord.Member, candy_id: str, qte: int = 1):
        """Retire un bonbon au membre"""
        if candy_id in CANDIES and qte > 0:
            inv = await self.config.member(user).inv()
            if candy_id in inv:
                if qte >= inv[candy_id]:
                    del inv[candy_id]
                else:
                    inv[candy_id] -= qte
                await self.config.member(user).inv.set(inv)
                return True
            return False
        raise InvalidCandy("Il n'y a aucun bonbon à ce nom ou la quantité est invalide")

    async def edit_candy(self, user: discord.Member, candy_id: str, qte: int):
        """Edite la quantité d'un bonbon possédé par le membre"""
        if candy_id in CANDIES and qte >= 0:
            inv = await self.config.member(user).inv()
            inv[candy_id] = qte
            await self.config.member(user).inv.set(inv)
            return True
        raise InvalidCandy("Il n'y a aucun bonbon à ce nom ou la quantité est invalide")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild:
            channel = message.channel
            cache = self.get_cache(message.guild)
            cache["spawn_counter"] += 1 if not random.randint(0, 2) else 0
            if cache["spawn_counter"] >= await self.config.guild(message.guild).spawn_counter_trigger():
                if time.time() > cache["last_spawn"] + await self.config.guild(message.guild).spawn_cooldown():
                    logger.info("Spawn lancé")
                    cache["last_spawn"] = time.time()
                    cache["spawn_counter"] = 0
                    await asyncio.sleep(random.randint(3, 15))
                    spawn_channel = message.guild.get_channel(await self.config.guild(message.guild).spawn_channel())
                    if spawn_channel:
                        type = random.choice(["fastest", "giveaway"])
                        if type == "fastest":
                            candy_id = random.choice(list(CANDIES.keys()))
                            candy = CANDIES[candy_id]
                            qt = random.randint(1, 3)
                            text = random.choice([
                                "Je donne {} au plus rapide ! Dépêchez-vous !",
                                "Voici {} ! Premier arrivé, premier servi.",
                                "_Lance {} sur le salon_",
                                "Nouvelle livraison de {} ! Cliquez vite."
                            ])
                            if qt > 1:
                                namef = "**{}** x{}".format(candy["name"], qt)
                            else:
                                namef = "**" + candy["name"] + "**"

                            emcolor = HALLOWEEN_COLOR()
                            em = discord.Embed(title="Récolte d'Halloween • Au plus rapide", description=text.format(namef),
                                               color=emcolor)
                            em.set_thumbnail(url=candy["img"])
                            em.set_footer(text="Soyez le premier à cliquer sur la réaction")

                            spawn = await spawn_channel.send(embed=em)
                            start_adding_reactions(spawn, ["🤲"])
                            try:
                                react, user = await self.bot.wait_for("reaction_add",
                                                                      check=lambda r, u: r.message.id == spawn.id and not u.bot,
                                                                      timeout=60)
                            except asyncio.TimeoutError:
                                await spawn.delete()
                                cache["spawn_counter"] = await self.config.guild(message.guild).spawn_counter_trigger() / 2
                                return
                            else:
                                await self.add_candy(user, candy_id, qt)
                                wintxt = random.choice([
                                    "{0} empoche {1} avec succès !",
                                    "C'est {0} qui partira donc avec {1} !",
                                    "{0} a été le/la plus rapide, repartant avec {1}.",
                                    "Bien joué {0} ! Tu pars avec {1}.",
                                    "Bravo à {0} qui repart avec {1}."
                                ])
                                post_em = discord.Embed(title="Récolte d'Halloween • Au plus rapide", description=wintxt.format(user.mention, namef),
                                                       color=emcolor)
                                post_em.set_thumbnail(url=candy["img"])
                                post_em.set_footer(text="ASTUCE · " + random.choice(ASTUCES))
                                await spawn.edit(embed=post_em)
                                await spawn.remove_reaction("🤲", self.bot.user)
                                await spawn.delete(delay=10)
                        else:
                            candies_id = random.sample(list(CANDIES.keys()), k=random.randint(2, 4))
                            text = random.choice([
                                "Je donne ces bonbons :\n",
                                "Voilà ce que je donne aujourd'hui :\n",
                                "Distribution générale ! Piochez là-dedans :\n",
                                "Je vous propose de piocher dans tout ça :\n"
                            ])
                            ctxt = ""
                            for c in candies_id:
                                candy = CANDIES[c]
                                ctxt += "- **{}**\n".format(candy["name"])

                            emcolor = HALLOWEEN_COLOR()
                            em = discord.Embed(title="Récolte d'Halloween • Distribution générale", description=text + ctxt,
                                               color=emcolor)
                            em.set_footer(text="Cliquez sur la réaction pour en obtenir un (au hasard)")

                            spawn = await spawn_channel.send(embed=em)
                            start_adding_reactions(spawn, ["🤲"])

                            cache["distrib_users"] = {}
                            cache["distrib_candies"] = candies_id
                            cache["distrib_msg"] = spawn.id
                            userlist = []
                            timeout = time.time() + 60
                            while time.time() < timeout and len(cache["distrib_users"]) < (len(candies_id) * 2):
                                if list(cache["distrib_users"].keys()) != userlist:
                                    userlist = list(cache["distrib_users"].keys())
                                    tabl = []
                                    for uid, gain in cache["distrib_users"].items():
                                        tabl.append((channel.guild.get_member(uid).name, CANDIES[gain]["name"]))
                                    nem = discord.Embed(title="Récolte d'Halloween • Distribution générale",
                                                       description=text + ctxt,
                                                       color=emcolor)
                                    nem.set_footer(text="Cliquez sur la réaction pour en obtenir un (au hasard)")
                                    nem.add_field(name="» Bonbons obtenus", value="```{}```".format(tabulate(tabl, headers=["Membre", "Bonbon"])))
                                    await spawn.edit(embed=nem)
                                await asyncio.sleep(0.5)
                            await spawn.delete()
                            if time.time() >= timeout and len(cache["distrib_users"]) >= (len(candies_id) * 2) :
                                end_msg = random.choice(["Distribution terminée, à la prochaine !",
                                                         "Temps écoulé, au revoir !",
                                                         "Trop tard, au revoir !"])
                            else:
                                end_msg = random.choice(["J'en ai plus donc ça se termine là. Bye !",
                                                         "Terminé, j'en ai plus à vous donner.",
                                                         "Je n'ai plus de bonbons à vous donner, au revoir !",
                                                         "Plus rien à donner, j'arrête la distribution."])
                            await spawn.remove_reaction("🤲", self.bot.user)
                            if cache["distrib_users"]:
                                tabl = []
                                for uid, gain in cache["distrib_users"].items():
                                    tabl.append((channel.guild.get_member(uid).name, CANDIES[gain]["name"]))
                                end_em = discord.Embed(title="Récolte d'Halloween • Distribution générale (terminée)",
                                                    description=end_msg,
                                                    color=emcolor)
                                end_em.set_footer(text="ASTUCE · " + random.choice(ASTUCES))
                                end_em.add_field(name="» Bonbons obtenus", value="```{}```".format(tabulate(tabl, headers=["Membre", "Bonbon"])))
                                await spawn_channel.send(embed=end_em, delete_delay=10)
                            else:
                                end_em = discord.Embed(title="Récolte d'Halloween • Distribution générale (terminée)",
                                                       description=end_msg,
                                                       color=emcolor)
                                end_em.set_footer(text="ASTUCE · " + random.choice(ASTUCES))
                                end_em.add_field(name="» Bonbons obtenus", value="Personne n'a participé à la distribution")
                                await spawn_channel.send(embed=end_em, delete_delay=10)
            status = self.get_member_status(message.author)
            if status["dur_haunt"]:
                if not random.randint(0, 4):
                    emojis = ["👻","💀","🎃","🐲","🤡"]
                    emoji = random.choice(emojis)
                    await message.add_reaction(emoji)
            if status["dur_ego"]:
                if not random.randint(0, 4):
                    emojis = ["😍","🥰","🤩","😎","🤘","👌","👀","💪","🙏"]
                    emoji = random.choice(emojis)
                    await message.add_reaction(emoji)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        message = reaction.message
        if message.guild:
            cache = self.get_cache(message.guild)
            if not user.bot:
                if message.id == cache["distrib_msg"]:
                    if reaction.emoji == "🤲":
                        if user.id not in cache["distrib_users"]:
                            candy = random.choice(cache["distrib_candies"])
                            await self.add_candy(user, candy, 1)
                            cache["distrib_users"][user.id] = candy

    @commands.Cog.listener()
    async def on_typing(self, channel, user, start):
        if channel.guild:
            status = self.get_member_status(user)
            if status["dur_ego"]:
                if time.time() >= status["ego_cd"]:
                    if not random.randint(0, 4):
                        status["ego_cd"] = time.time() + 45
                        txt = random.choice([
                            "Agenouillez-vous, **{}** va parler.",
                            "Notre maître à tous **{}** va parler :pray:...",
                            "Laissez place à **{}**.",
                            "Arrêtez-vous tous, **{}** est en train d'écrire...",
                            "Arrêtez-vous tous, **{}** va parler...",
                            "Mais 🤩 ?!?! **{}** va parler 🙏🙏🙏",
                            "Oh mon dieu !!! **{}** est en train d'écrire j'y crois pas 🤩 !",
                            "La star **{}** va parler ! Taisez-vous !"
                        ])
                        await channel.send(txt.format(user.display_name))

    def guess_candy(self, input: str):
        """Devine quel bonbon est demandé (fuzzywuzzy)"""
        candies = list(CANDIES.keys())
        return process.extractOne(input.lower(), candies)[0]

    async def get_rainbow_roles(self, guild: discord.Guild):
        roles = await self.config.guild(guild).rainbow_roles()
        ordre = ["red", "orange", "yellow", "green", "blue", "purple"]
        all_roles = []
        for r in roles:
            if roles[r]:
                all_roles.append([ordre.index(r), guild.get_role(roles[r])])
        if len(all_roles) == 6:
            so = sorted(all_roles, key=operator.itemgetter(0))
            return [i[1] for i in so]
        return None

    async def manage_effects(self, ctx, candy_id: str, exclude_effects: list = None):
        user = ctx.author
        candy = CANDIES[candy_id]
        status = self.get_member_status(user)
        if status["dur_malus"] != 0:
            return await ctx.send("**Vous êtes malade** • Vous ne pouvez plus manger de bonbons pendant quelques minutes...")
        effect = random.choices(candy["ep"], candy["ew"], k=1)[0]
        if exclude_effects:
            if effect in exclude_effects:
                effect = "none"
        if effect == "none":
            await self.remove_candy(user, candy_id)
            async with ctx.channel.typing():
                await asyncio.sleep(random.randint(1, 3))
                result = random.choice([
                    "Vous dégustez votre bonbon mais vous ne ressentez aucun effet particulier.",
                    "Bonbon absolument délicieux, mais sans aucun effet particulier.",
                    "Super bonbon, mais sans effet.",
                    "Vous ne remarquez aucun effet particulier en dégustant ce bonbon...",
                    "Vous consommez le bonbon. Aucun effet ne semble s'en dégager.",
                    "Délicieux. Aucun effet néanmoins."
                ])
                em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                em.set_author(name=user.name, icon_url=user.avatar_url)
                em.set_footer(text="Vous mangez x1 {}".format(candy["name"].lower()))
                await ctx.send(embed=em)
                return True
        elif effect == "flip":
            async with ctx.channel.typing():
                await asyncio.sleep(random.randint(2, 5))
                result = random.choice([
                    "Vous avez soudainement le tournis...",
                    "Vous vous sentez soudainement renversé...",
                    "Une sensation de vertige vous prend violemment...",
                    "Vous vous sentez pas très bien..."
                ])
                em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                em.set_author(name=user.name, icon_url=user.avatar_url)
                em.set_footer(text="Vous mangez x1 {}".format(candy["name"].lower()))
            if not status["dur_flip"]:
                original = user.display_name
                char = "abcdefghijklmnopqrstuvwxyz"
                tran = "ɐqɔpǝɟƃɥᴉɾʞlɯuodbɹsʇnʌʍxʎz"
                table = str.maketrans(char, tran)
                name = user.display_name.translate(table)
                char = char.upper()
                tran = "∀qƆpƎℲפHIſʞ˥WNOԀQᴚS┴∩ΛMX⅄Z"
                table = str.maketrans(char, tran)
                name = name.translate(table)
                try:
                    await user.edit(nick=name, reason="Effet event d'halloween")
                except:
                    return await self.manage_effects(ctx, candy_id, exclude_effects=["flip"])
                await ctx.send(embed=em)
                await self.remove_candy(user, candy_id)
                status["dur_flip"] = BASE_DURATIONS["flip"]
                basetime = time.time()
                while time.time() <= (basetime + self.get_member_status(user)["dur_flip"]):
                    await asyncio.sleep(5)
                await user.edit(nick=original, reason="Fin d'effet")
                status["dur_flip"] = 0
            else:
                await ctx.send(embed=em)
                await self.remove_candy(user, candy_id)
                status["dur_flip"] += BASE_DURATIONS["flip"] / 2
        elif effect == "rainbow":
            roles = await self.get_rainbow_roles(ctx.guild)
            if roles:
                async with ctx.channel.typing():
                    await asyncio.sleep(random.randint(2, 5))
                    result = random.choice([
                        "Une énergie soudaine parcours votre corps...",
                        "Vous vous sentez en pleine forme, le bonbon semble vous avoir donné une certaine énergie...",
                        "Vous brillez de mille feux !",
                        "Une vague d'énergie vous traverse, vous brillez de toutes les couleurs !",
                        "https://www.youtube.com/watch?v=OSyp7VGYen8",
                        "Ce bonbon au goût étrange ne vous donne pas d'aîles mais vous fait briller de toutes les couleurs !"
                    ])
                    em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                    em.set_author(name=user.name, icon_url=user.avatar_url)
                    em.set_footer(text="Vous mangez x1 {}".format(candy["name"].lower()))
                    await ctx.send(embed=em)
                if not status["dur_rainbow"]:
                    await self.remove_candy(user, candy_id)
                    status["dur_rainbow"] = BASE_DURATIONS["rainbow"]
                    def cycle_roles(last: discord.Role = None):
                        if last:
                            i = roles.index(last)
                            next = i + 1 if len(roles) > i + 1 else 0
                            return roles[next]
                        return roles[0]
                    new_role = old_role = None
                    basetime = time.time()
                    while time.time() <= (basetime + self.get_member_status(user)["dur_rainbow"]):
                        if old_role:
                            await user.remove_roles(old_role, reason="Effet d'event halloween")
                            new_role = cycle_roles(old_role)
                            await user.add_roles(new_role, reason="Effet d'event halloween")
                        else:
                            new_role = cycle_roles()
                            await user.add_roles(new_role, reason="Effet d'event halloween")
                        await asyncio.sleep(30)
                        old_role = new_role
                    if old_role:
                        await user.remove_roles(old_role, reason="Fin effet d'event halloween")
                    status["dur_rainbow"] = 0
                    return True
                else:
                    await self.remove_candy(user, candy_id)
                    status["dur_rainbow"] += BASE_DURATIONS["rainbow"] / 2
            else:
                async with ctx.channel.typing():
                    await asyncio.sleep(random.randint(1, 3))
                    result = random.choice([
                        "Rien ne se produit. (L'effet que vous auriez dû avoir n'est pas configuré)",
                        "??? Il semblerait que l'effet n'a pas marché (il n'est pas configuré correctement)"
                    ])
                    em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                    em.set_author(name=user.name, icon_url=user.avatar_url)
                    em.set_footer(text="Vous ne perdez pas votre bonbon")
                    await ctx.send(embed=em)
        elif effect == "haunt":
            async with ctx.channel.typing():
                await asyncio.sleep(random.randint(2, 5))
                result = random.choice([
                    "Vous sentez une étrange présence avec vous...",
                    "Vous vous sentez surveillé soudainement...",
                    "On dirait qu'un esprit vous surveille...",
                    "Vous êtes hanté !",
                    "Ce bonbon était hanté !"
                ])
                em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                em.set_author(name=user.name, icon_url=user.avatar_url)
                em.set_footer(text="Vous mangez x1 {}".format(candy["name"].lower()))
                await ctx.send(embed=em)
            if not status["dur_haunt"]:
                await self.remove_candy(user, candy_id)
                status["dur_haunt"] = BASE_DURATIONS["haunt"]
                basetime = time.time()
                while time.time() <= (basetime + self.get_member_status(user)["dur_haunt"]):
                    await asyncio.sleep(5)
                status["dur_haunt"] = 0
            else:
                await self.remove_candy(user, candy_id)
                status["dur_haunt"] += BASE_DURATIONS["haunt"] / 2
        elif effect == "fortune":
            await self.remove_candy(user, candy_id)
            await asyncio.sleep(random.randint(2, 5))
            new_candy_id = random.choice(list(CANDIES.keys()))
            new_candy = CANDIES[new_candy_id]
            qte = random.randint(2, 5)
            await self.add_candy(user, new_candy_id, qte)
            text = random.choice([
                "Coup de chance ! **{0}** x{1} vous tombe comme par magie dans les mains !",
                "Quelle chance ! Un inconnu vous donne **{0}** x{1} en plus !",
                "Vous trébuchez sur un paquet de **{0}** x{1} en mangeant {2} !",
                "On dirait que la chance vous sourit, vous recevez un bonus de {1} **{0}** !",
                "Vous étiez tranquille, à déguster votre bonbon et soudain... **{0}** x{1} tombe du ciel !"
            ])
            em = discord.Embed(description=text.format(new_candy["name"], qte, candy["name"]), color=HALLOWEEN_COLOR())
            em.set_author(name=user.name, icon_url=user.avatar_url)
            em.set_footer(text="Vous mangez x1 {}".format(candy["name"].lower()))
            await ctx.send(embed=em)
        elif effect == "ego":
            async with ctx.channel.typing():
                await asyncio.sleep(random.randint(2, 5))
                result = random.choice([
                    "Vous attirez de bons esprits à vous...",
                    "Vous sentez soudainement une bonne énergie vous suivre...",
                    "Un bon esprit vous suit...",
                    "On dirait que la chance vous sourit...",
                    "Vous sentez une présence agréable à vos côtés...",
                    "Ce bonbon vous fait prendre un melon énorme...",
                    "Vous vous sentez soudainement célèbre et important.",
                    "Vous semblez devenir temporairement une e-pop.",
                    "Les esprits des anciens White knights vous suivent..."
                ])
                em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                em.set_author(name=user.name, icon_url=user.avatar_url)
                em.set_footer(text="Vous mangez x1 {}".format(candy["name"].lower()))
                await ctx.send(embed=em)
            if not status["dur_ego"]:
                await self.remove_candy(user, candy_id)
                status["dur_ego"] = BASE_DURATIONS["ego"]
                basetime = time.time()
                while time.time() <= (basetime + self.get_member_status(user)["dur_ego"]):
                    await asyncio.sleep(5)
                status["dur_ego"] = 0
            else:
                await self.remove_candy(user, candy_id)
                status["dur_ego"] += BASE_DURATIONS["ego"]
        elif effect == "loss":
            await self.remove_candy(user, candy_id)
            inv = await self.config.member(user).inv()
            if inv:
                rdn = random.choice(list(inv.keys()))
                max_qte = inv[rdn]
                if max_qte > 1:
                    loss = random.randint(1, int(max_qte / 2))
                else:
                    loss = 1
                async with ctx.channel.typing():
                    await asyncio.sleep(random.randint(2, 5))
                    result = random.choice([
                        "Oh non ! Vous perdez x{1} **{0}** !",
                        "Vous faîtes une indigestion ! Vous décidez de jeter **{0}** x{1}...",
                        "Ce bonbon était maudit... Vous perdez x{1} **{0}**...",
                        "C'était pas bon et en plus vous avez perdu x{1} **{0}** dans votre confusion."
                    ])
                    em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                    em.set_author(name=user.name, icon_url=user.avatar_url)
                    em.set_footer(text="Vous mangez x1 {}".format(candy["name"].lower()))
                    await ctx.send(embed=em)
                await self.remove_candy(user, rdn, loss)
            else:
                async with ctx.channel.typing():
                    await asyncio.sleep(random.randint(2, 5))
                    result = random.choice([
                        "C'était pas bon, mais aucun effet à constater...",
                        "Ce bonbon devait avoir trainé quelque part... Mais aucun malus particulier.",
                        "Horrible celui-ci, mais rien à signaler.",
                        "Vous êtes à deux doigts de tomber malade, mais vous n'avez aucun effet particulier non plus.",
                        "C'était pas terrible, mais à part ça rien de spécial..."
                    ])
                    em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                    em.set_author(name=user.name, icon_url=user.avatar_url)
                    em.set_footer(text="Vous mangez x1 {}".format(candy["name"].lower()))
                    await ctx.send(embed=em)
        elif effect == "malus":
            loss = random.randint(1, 5)
            score = await self.config.member(user).score()
            if score <= loss:
                score = 0
            else:
                score -= loss
            await self.config.member(user).score.set(score)

            async with ctx.channel.typing():
                await asyncio.sleep(random.randint(2, 5))
                result = random.choice([
                    "Vous êtes tombé malade... Vous n'arrivez plus à faire quoi que ce soit.",
                    "Vous vous sentez mal... le bonbon était de toute évidence plus bon du tout.",
                    "Oups, il semblerait que ce bonbon vous ai rendu malade...",
                    "Vous tombez malade : impossible de manger quoi que ce soit..."
                ])
                em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                em.set_author(name=user.name, icon_url=user.avatar_url)
                em.set_footer(text="Vous mangez x1 {} — Vous perdez {} points".format(candy["name"].lower(), loss))
                await ctx.send(embed=em)
            if not status["dur_malus"]:
                await self.remove_candy(user, candy_id)
                status["dur_malus"] = BASE_DURATIONS["malus"]
                basetime = time.time()
                while time.time() <= (basetime + self.get_member_status(user)["dur_malus"]):
                    await asyncio.sleep(5)
                status["dur_malus"] = 0
            else:
                await self.remove_candy(user, candy_id)
                status["dur_malus"] += BASE_DURATIONS["malus"] / 4
        else:
            role_id = await self.config.guild(ctx.guild).room_role()
            if role_id:
                async with ctx.channel.typing():
                    await asyncio.sleep(random.randint(2, 5))
                    result = random.choice([
                        "Hmm. Il semblerait que vous aviez débloqué un secret... Observez bien.",
                        "Vous avez débloqué un secret. Regardez bien.",
                        "Vous avez désormais accès à un secret...",
                        "Oh, vous avez débloqué un secret. Observez bien..."
                    ])
                    em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                    em.set_author(name=user.name, icon_url=user.avatar_url)
                    em.set_footer(text="Vous mangez x1 {}".format(candy["name"].lower()))
                    await ctx.send(embed=em)
                if not status["dur_room"]:
                    await self.remove_candy(user, candy_id)
                    status["dur_room"] = BASE_DURATIONS["room"]
                    role = ctx.guild.get_role(role_id)
                    await user.add_roles(role, reason="Effet event d'halloween")
                    basetime = time.time()
                    while time.time() <= (basetime + self.get_member_status(user)["dur_room"]):
                        await asyncio.sleep(5)
                    status["dur_room"] = 0
                    await user.remove_roles(role, reason="Fin effet event d'halloween")
                else:
                    await self.remove_candy(user, candy_id)
                    status["dur_room"] += BASE_DURATIONS["room"] / 2
            else:
                async with ctx.channel.typing():
                    await asyncio.sleep(random.randint(1, 3))
                    result = random.choice([
                        "Rien ne se produit. (L'effet que vous auriez dû avoir n'est pas configuré)",
                        "??? Il semblerait que l'effet n'a pas marché (il n'est pas configuré correctement)"
                    ])
                    em = discord.Embed(description=result, color=HALLOWEEN_COLOR())
                    em.set_author(name=user.name, icon_url=user.avatar_url)
                    em.set_footer(text="Vous ne perdez pas votre bonbon")
                    await ctx.send(embed=em)

    @commands.command(aliases=["mange"])
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.member)
    async def eat(self, ctx, *candy):
        """Manger un bonbon de votre inventaire

        Affiche l'inventaire si vous ne précisez aucun bonbon"""
        author = ctx.author
        if candy:
            candy = " ".join(candy)
            candy_id = self.guess_candy(candy)
            inv = await self.config.member(author).inv()
            if candy_id in inv:
                await self.manage_effects(ctx, candy_id)
            else:
                await ctx.send("**Introuvable** • Vous ne possédez pas *{}*".format(CANDIES[candy_id]["name"]))
        else:
            inv = await self.config.member(author).inv()
            if inv:
                items = []
                for i in inv:
                    items.append([CANDIES[i]["name"], inv[i]])
                tabl = "```{}```".format(tabulate(items, headers=["Bonbon", "Quantité"]))
                em = discord.Embed(title="Votre inventaire", description=tabl, color=HALLOWEEN_COLOR())
                em.set_footer(text="Pour en manger un, faîtes ;eat <bonbon>")
                await ctx.send(embed=em)
            else:
                await ctx.send("**Inventaire vide** • Essayez d'avoir des bonbons !")

    @commands.command(name="poche", aliases=["poches"])
    @commands.guild_only()
    async def _inv_candy(self, ctx):
        """Voir son inventaire de bonbons"""
        inv = await self.config.member(ctx.author).inv()
        if inv:
            items = []
            for i in inv:
                items.append([CANDIES[i]["name"], inv[i]])
            tabl = "```{}```".format(tabulate(items, headers=["Bonbon", "Quantité"]))
            status = self.get_member_status(ctx.author)
            st = []
            for e in status:
                if e.startswith("dur"):
                    if status[e] > 0:
                        st.append("`" + EFFECT_TRAD_FR[e] + "`")
            stats = "**Effets en cours** · {}\n" \
                    "**Score** · {}\n\n".format(" ".join(st) if st else "Aucun", await self.config.member(ctx.author).score())
            em = discord.Embed(title="Votre inventaire", description=stats + tabl, color=HALLOWEEN_COLOR())
            em.set_footer(text="Pour en manger un, faîtes ;eat <bonbon>")
            await ctx.send(embed=em)
        else:
            status = self.get_member_status(ctx.author)
            st = []
            for e in status:
                if e.startswith("dur"):
                    if status[e] > 0:
                        st.append("`" + EFFECT_TRAD_FR[e] + "`")
            stats = "**Effets en cours** · {}\n" \
                    "**Score** · {}\n\n".format(" ".join(st) if st else "Aucun",
                                              await self.config.member(ctx.author).score())
            em = discord.Embed(title="Votre inventaire", description=stats + "**Inventaire vide**", color=HALLOWEEN_COLOR())
            em.set_footer(text="Essayez de gagner des bonbons en les attrapant sur les salons écrits !")
            await ctx.send(embed=em)

    @commands.command(name="gift", aliases=["cadeau"])
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.member)
    async def _give_candy(self, ctx, user: discord.Member, candy: str, qte: int = 1):
        """Donner un/des bonbon(s) à un membre

        Si vous ne précisez pas de quantité, vous ne donnez qu'un seul bonbon"""
        authorinv = await self.config.member(ctx.author).inv()
        candy_id = self.guess_candy(candy)
        if candy_id in authorinv:
            candy_name = CANDIES[candy_id]["name"]
            if await self.enough_candies(ctx.author, candy_id, qte):
                await self.remove_candy(ctx.author, candy_id, qte)
                await self.add_candy(user, candy_id, qte)
                await ctx.send(f"**Don réalisé** • {candy_name} x{qte} ont été donnés à {user.mention}")
            else:
                await ctx.send(f"**Don impossible** • Vous ne possédez pas autant de ce bonbon : {candy_name}")
        else:
            await ctx.send(f"**Don impossible** • Bonbon introuvable ou non possédé")

    @commands.command(name="topevent")
    @commands.guild_only()
    async def _top_hw(self, ctx):
        """Affiche le top global"""
        members = await self.config.all_members(ctx.guild)
        before = []
        for m in members:
            before.append([ctx.guild.get_member(m).name, members[m]["score"]])
        if before:
            after = sorted(before, key=operator.itemgetter(1), reverse=True)
            tabl = "```{}```".format(tabulate(after, headers=["Membre", "Score"]))
            em = discord.Embed(title="Top sur {} • Event d'Halloween".format(ctx.guild.name), description=tabl, color=HALLOWEEN_COLOR())
            await ctx.send(embed=em)
        else:
            await ctx.send("Aucun top à afficher")

    @commands.group(name="hwset")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_messages=True)
    async def _halloween_set(self, ctx):
        """Commandes de gestion de l'event d'Halloween"""

    @_halloween_set.command()
    async def spawncounter(self, ctx, val: int):
        """Modifie la base de comptage utilisée pour faire spawn des bonbons sur le salon de spawn

        Doit être compris entre 25 et 500"""
        guild = ctx.guild
        if 25 <= val <= 500:
            await self.config.guild(guild).spawn_counter_trigger.set(val)
            await ctx.send(f"**Valeur modifiée** • Le trigger se lancera sur une base de *{val}*")
        else:
            await ctx.send(f"**Valeur invalide** • La valeur doit être comprise entre 25 et 500.")

    @_halloween_set.command()
    async def spawncd(self, ctx, val: int):
        """Modifie le cooldown (en secondes) entre deux spawn

        Doit être supérieur à 10 (secondes)"""
        guild = ctx.guild
        if 10 <= val:
            await self.config.guild(guild).spawn_cooldown.set(val)
            await ctx.send(f"**Valeur modifiée** • Il y aura un cooldown de *{val}* secondes entre deux spawns (minimum)")
        else:
            await ctx.send(f"**Valeur invalide** • La valeur doit être supérieure à 10 (secondes).")

    @_halloween_set.command()
    async def spawnchannel(self, ctx, channel: discord.TextChannel = None):
        """Défini le salon écrit utilisé pour faire spawner les bonbons"""
        guild = ctx.guild
        if channel:
            await self.config.guild(guild).spawn_channel.set(channel.id)
            await ctx.send(f"**Salon modifié** • Les bonbons apparaissent désormais sur {channel.mention}")
        else:
            await self.config.guild(guild).spawn_channel.set(None)
            await ctx.send(f"**Salon retiré** • Plus aucun bonbon n'apparaîtra sur ce serveur.")

    @_halloween_set.command()
    async def rainbowroles(self, ctx,
                           red: discord.Role = None,
                           orange: discord.Role = None,
                           yellow: discord.Role = None,
                           green: discord.Role = None,
                           blue: discord.Role = None,
                           purple: discord.Role = None):
        """Lie 6 rôles (rouge, orange, jaune, vert, bleu et violet) pour l'effet arc-en-ciel

        Assurez-vous que les rôles soient au dessus des autres rôles communs des membres (et sans droits particuliers)"""
        guild = ctx.guild
        if all([red, orange, yellow, green, blue, purple]):
            set_roles = await self.config.guild(guild).rainbow_roles()
            set_roles["red"] = red.id
            set_roles["orange"] = orange.id
            set_roles["yellow"] = yellow.id
            set_roles["green"] = green.id
            set_roles["blue"] = blue.id
            set_roles["purple"] = purple.id
            await self.config.guild(guild).rainbow_roles.set(set_roles)
            await ctx.send(f"**Rôles modifiés** • Ces rôles ont été liés pour faire fonctionner l'effet Rainbow.")
        else:
            await self.config.guild(guild).rainbow_roles.set({"red": None, "orange": None, "yellow": None,
                                                              "green": None, "blue": None, "purple": None})
            await ctx.send(f"**Rôles retirés** • L'effet rainbow n'est plus configuré.")

    @_halloween_set.command()
    async def roomrole(self, ctx, role: discord.Role = None):
        """Défini le rôle pour accéder au salon secret

        Le rôle est retiré si aucun n'est précisé dans la commande"""
        guild = ctx.guild
        if role:
            await self.config.guild(guild).room_role.set(role.id)
            await ctx.send(f"**Rôle modifié** • Ce rôle servira à donner l'accès au salon secret voulu.")
        else:
            await self.config.guild(guild).room_role.set(None)
            await ctx.send(f"**Rôle retiré** • Le salon secret est désactivé.")

    @_halloween_set.command()
    async def resetuser(self, ctx, user: discord.Member):
        """Reset les effets d'un utilisateur"""
        self.get_member_status(user, reset=True)
        await ctx.send(f"Reset des status de {user.name} réalisé.")

    @_halloween_set.command()
    async def resetguild(self, ctx):
        """Reset le cache du serveur"""
        self.get_cache(ctx.guild, reset=True)
        await ctx.send(f"Reset du cache réalisé.")

    @_halloween_set.command()
    @checks.is_owner()
    async def setcounter(self, ctx, val: int):
        """Modifie le counter du cache de ce serveur"""
        self.get_cache(ctx.guild)["spawn_counter"] = val
        await ctx.send(f"Valeur `spawn_counter` modifiée pour {val}")

    @_halloween_set.command()
    @checks.is_owner()
    async def setlastspawn(self, ctx, val: int):
        """Modifie le last_spawn du cache de ce serveur"""
        self.get_cache(ctx.guild)["last_spawn"] = val
        await ctx.send(f"Valeur `last_spawn` modifiée pour {val}")

    @_halloween_set.command(aliases=["suf"])
    @checks.is_owner()
    async def setusereffect(self, ctx, user: discord.Member, effect: str, val: int):
        """Modifie la valeur d'un effet d'un membre"""
        user_status = self.get_member_status(user)
        if effect.lower() in user_status:
            user_status[effect.lower()] = val
            await ctx.send(f"Valeur `{effect}` de {user.name} modifiée pour {val}")
        else:
            await ctx.send("Nom d'effet inconnu")


