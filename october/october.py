import asyncio
import logging
import operator
import random
import time

import discord
from fuzzywuzzy import process
from redbot.core import Config, commands
from redbot.core.utils.menus import start_adding_reactions
from tabulate import tabulate

logger = logging.getLogger("red.zaap-plugins.october")

HALLOWEEN_COLOR = lambda: random.choice([0x5E32BA, 0xEB6123, 0x18181A, 0x96C457])

CANDIES = {
    "berlingot": {"name": "Berlingot", "ep": ["none", "rainbow"], "ew": [3, 1, 2],
                  "img": ""},
    "marshmallow": {"name": "Marshmallow", "ep": ["none", "haunt", "ego"], "ew": [3, 2, 1],
                    "img": ""},
    "calisson": {"name": "Calisson", "ep": ["none", "fortune", "flip"], "ew": [2, 1, 2],
                 "img": ""},
    "caramel": {"name": "Caramel", "ep": ["haunt", "ego"], "ew": [3, 1, 2],
                "img": ""},
    "chewinggum": {"name": "Chewing-gum", "ep": ["none", "room", "malus"], "ew": [3, 1, 1],
                   "img": ""},
    "dragee": {"name": "Dragée", "ep": ["none", "rainbow", "loss"], "ew": [3, 1, 2],
               "img": ""},
    "guimauve": {"name": "Guimauve", "ep": ["none", "loss", "fortune"], "ew": [1, 1, 1],
                 "img": ""},
    "reglisse": {"name": "Réglisse", "ep": ["malus", "flip"], "ew": [2, 1, 3],
                 "img": ""},
    "sucette": {"name": "Sucette", "ep": ["room", "ego", "haunt"], "ew": [2, 1, 2],
                "img": ""},
    "nougat": {"name": "Nougat", "ep": ["none", "rainbow"], "ew": [3, 2],
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
    "Il y a 2 types de dons de bonbons : 'Au plus rapide' et 'Distribution générale'",
    "Ceci n'est pas une astuce",
    "Les bonbons virtuels ne donnent pas de caries",
    "Si vous mangez trop de bonbons, vous allez devenir e-diabétique"
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

    def get_cache(self, guild: discord.Guild):
        if guild.id not in self.cache:
            self.cache[guild.id] = {"spawn_counter": 0,
                                    "last_spawn": time.time(),

                                    "distrib_msg": None,
                                    "distrib_users": {},
                                    "distrib_candies": []}
        return self.cache[guild.id]

    def get_member_status(self, user: discord.Member):
        guild = user.guild
        if guild.id not in self.status:
            self.status[guild.id] = {}
        if user.id not in self.status[guild.id]:
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
                    cache["last_spawn"] = time.time()
                    cache["spawn_counter"] = 0
                    spawn_channel = message.guild.get_channel(await self.config.guild(message.guild).spawn_channel())
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
                                                                  check=lambda r: r.message.id == spawn.id,
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
                            ctxt = "- **{}**\n".format(candy["name"])

                        emcolor = HALLOWEEN_COLOR()
                        em = discord.Embed(title="Récolte d'Halloween • Distribution générale", description=text + ctxt,
                                           color=emcolor)
                        em.set_footer(text="Cliquez sur la réaction pour en obtenir un (au hasard)")

                        spawn = await spawn_channel.send(embed=em)
                        start_adding_reactions(spawn, ["🤲"])

                        cache["distrib_users"] = []
                        cache["distrib_candies"] = candies_id
                        cache["distrib_msg"] = spawn.id
                        userlist = []
                        timeout = time.time() + 60
                        while time.time() < timeout and len(cache["distrib_users"]) < (len(candies_id) * 2):
                            if cache["distrib_users"].keys() != userlist:
                                userlist = cache["distrib_users"]
                                tabl = []
                                for uid, gain in cache["distrib_users"].iteritems():
                                    tabl.append((channel.guild.get_member(uid).mention, CANDIES[gain]["name"]))
                                nem = discord.Embed(title="Récolte d'Halloween • Distribution générale",
                                                   description=text + ctxt,
                                                   color=emcolor)
                                nem.set_footer(text="Cliquez sur la réaction pour en obtenir un (au hasard)")
                                nem.add_field(name="— Obtenus —", value="```{}```".format(tabulate(tabl, headers=["Membre", "Bonbon"])))
                                await spawn.edit(embed=nem)
                            await asyncio.sleep(1)
                        await spawn.delete()
                        if time.time() >= timeout and len(cache["distrib_users"]):
                            end_msg = random.choice(["Distribution terminée, à la prochaine !",
                                                     "Temps écoulé, au revoir !",
                                                     "Trop tard, au revoir !"])
                        else:
                            end_msg = random.choice(["J'en ai plus donc ça se termine là. Bye !",
                                                     "Terminé, j'en ai plus à vous donner.",
                                                     "Je n'ai plus de bonbons à vous donner, au revoir !",
                                                     "Plus rien à donner, j'arrête la distribution."])
                        if cache["distrib_users"]:
                            tabl = []
                            for uid, gain in cache["distrib_users"].iteritems():
                                tabl.append((channel.guild.get_member(uid).mention, CANDIES[gain]["name"]))
                            end_em = discord.Embed(title="Récolte d'Halloween • Distribution générale (terminée)",
                                                description=end_msg,
                                                color=emcolor)
                            end_em.set_footer(text="ASTUCE · " + random.choice(ASTUCES))
                            end_em.add_field(name="— Obtenus —", value="```{}```".format(tabulate(tabl, headers=["Membre", "Bonbon"])))
                            await spawn_channel.send(embed=end_em, delete_delay=10)
                        else:
                            end_em = discord.Embed(title="Récolte d'Halloween • Distribution générale (terminée)",
                                                   description=end_msg,
                                                   color=emcolor)
                            end_em.set_footer(text="ASTUCE · " + random.choice(ASTUCES))
                            end_em.add_field(name="— Obtenus —", value="Personne n'a participé à la distribution")
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
            if message.id == cache["distrib_msg"]:
                if reaction.emoji == "🤲":
                    if user.id not in cache["distrib_users"]:
                        candy = random.choice(cache["distrib_candies"])
                        await self.add_candy(user, candy, 1)
                        cache["distrib_users"].append(user.id)

    @commands.Cog.listener()
    async def on_typing(self, channel, user, start):
        if channel.guild:
            status = self.get_member_status(user)
            if status["dur_ego"]:
                if time.time() >= status["ego_cd"]:
                    if not random.randint(0, 4):
                        status["ego_cd"] = time.time() + 30
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

    @commands.group(name="halloween", aliases=["hw"])
    @commands.guild_only()
    async def _halloween(self, ctx):
        """Commandes de l'event d'Halloween"""

    def guess_candy(self, input: str):
        """Devine quel bonbon est demandé (fuzzywuzzy)"""
        candies = list(CANDIES.keys())
        return process.extractOne(input.lower(), candies)[0]

    async def get_rainbow_roles(self, guild: discord.Guild):
        roles = await self.config.guild(guild).rainbow_roles()
        all_roles = []
        for r in roles:
            if roles[r]:
                all_roles.append([r, guild.get_role(roles[r])])
        if len(all_roles) == 6:
            so = sorted(all_roles, key=operator.itemgetter(0), reverse=True)
            return [i[1] for i in so]
        return None

    async def manage_effects(self, ctx, candy_id: str):
        user = ctx.author
        candy = CANDIES[candy_id]
        status = self.get_member_status(user)
        if status["dur_malus"] != 0:
            return await ctx.send("**Vous êtes malade** • Vous ne pouvez plus manger de bonbons pendant quelques minutes...")
        effect = random.choices(candy["ep"], candy["ew"], k=1)
        if effect == "none":
            await self.remove_candy(user, candy_id)
            async with ctx.channel.typing():
                await asyncio.sleep(random.randint(2, 5))
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
                em.set_footer(text="Vous mangez x1 {}".format(candy["name"]))
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
                em.set_footer(text="Vous mangez x1 {}".format(candy["name"]))
                await ctx.send(embed=em)
            if not status["dur_flip"]:
                await self.remove_candy(user, candy_id)
                original = user.display_name
                char = "abcdefghijklmnopqrstuvwxyz"
                tran = "ɐqɔpǝɟƃɥᴉɾʞlɯuodbɹsʇnʌʍxʎz"
                table = str.maketrans(char, tran)
                name = user.display_name.translate(table)
                char = char.upper()
                tran = "∀qƆpƎℲפHIſʞ˥WNOԀQᴚS┴∩ΛMX⅄Z"
                table = str.maketrans(char, tran)
                name = name.translate(table)
                await user.edit(nick=name, reason="Effet event d'halloween")
                status["dur_flip"] = BASE_DURATIONS["flip"]
                basetime = time.time()
                while time.time() <= (basetime + status["dur_flip"]):
                    await asyncio.sleep(5)
                await user.edit(nick=original, reason="Fin d'effet")
                status["dur_flip"] = 0
            else:
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
                    em.set_footer(text="Vous mangez x1 {}".format(candy["name"]))
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
                    while time.time() <= (basetime + status["dur_rainbow"]):
                        await asyncio.sleep(30)
                        if old_role:
                            await user.remove_roles([old_role], reason="Effet d'event halloween")
                            new_role = cycle_roles(old_role)
                            await user.add_roles([new_role], reason="Effet d'event halloween")
                        else:
                            new_role = cycle_roles()
                            await user.add_roles([new_role], reason="Effet d'event halloween")
                        old_role = new_role
                    if old_role:
                        await user.remove_roles([old_role], reason="Fin effet d'event halloween")
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
                    em.set_footer(text="Vous ne perdez pas votre bonbon".format(candy["name"]))
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
                em.set_footer(text="Vous mangez x1 {}".format(candy["name"]))
                await ctx.send(embed=em)
            if not status["dur_haunt"]:
                await self.remove_candy(user, candy_id)
                status["dur_haunt"] = BASE_DURATIONS["haunt"]
                basetime = time.time()
                while time.time() <= (basetime + status["dur_haunt"]):
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
            em.set_footer(text="Vous mangez x1 {}".format(candy["name"]))
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
                em.set_footer(text="Vous mangez x1 {}".format(candy["name"]))
                await ctx.send(embed=em)
            if not status["dur_ego"]:
                await self.remove_candy(user, candy_id)
                status["dur_ego"] = BASE_DURATIONS["ego"]
                basetime = time.time()
                while time.time() <= (basetime + status["dur_ego"]):
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
                loss = random.randint(1, int(max_qte / 2))
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
                    em.set_footer(text="Vous mangez x1 {}".format(candy["name"]))
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
                    em.set_footer(text="Vous mangez x1 {}".format(candy["name"]))
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
                em.set_footer(text="Vous mangez x1 {} — Vous perdez {} points".format(candy["name"], loss))
                await ctx.send(embed=em)
            if not status["dur_malus"]:
                await self.remove_candy(user, candy_id)
                status["dur_malus"] = BASE_DURATIONS["malus"]
                basetime = time.time()
                while time.time() <= (basetime + status["dur_malus"]):
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
                    em.set_footer(text="Vous mangez x1 {}".format(candy["name"]))
                    await ctx.send(embed=em)
                if not status["dur_room"]:
                    await self.remove_candy(user, candy_id)
                    status["dur_room"] = BASE_DURATIONS["room"]
                    role = ctx.guild.get_role(role_id)
                    await user.add_roles([role], reason="Effet event d'halloween")
                    basetime = time.time()
                    while time.time() <= (basetime + status["dur_room"]):
                        await asyncio.sleep(5)
                    status["dur_room"] = 0
                    await user.remove_roles([role], reason="Fin effet event d'halloween")
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
                    em.set_footer(text="Vous ne perdez pas votre bonbon".format(candy["name"]))
                    await ctx.send(embed=em)

    @_halloween.command(aliases=["mange"])
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.member)
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
                await ctx.send("**Introuvable** • Vous ne possédez pas *{}*".format(candy["name"]))
        else:
            inv = await self.config.member(author).inv()
            if inv:
                items = []
                for i in inv:
                    items.append([i, inv[i]])
                tabl = "```{}```".format(tabulate(items, headers=["Bonbon", "Quantité"]))
                em = discord.Embed(title="Votre inventaire", description=tabl, color=HALLOWEEN_COLOR())
                em.set_footer(text="Pour en manger un, faîtes ;eat <bonbon>")
                await ctx.send(embed=em)
            else:
                await ctx.send("**Inventaire vide** • Essayez d'avoir des bonbons !")

    @_halloween.command(name="inv")
    @commands.guild_only()
    async def _inv_candy(self, ctx):
        """Voir son inventaire de bonbons"""
        inv = await self.config.member(ctx.author).inv()
        if inv:
            items = []
            for i in inv:
                items.append([i, inv[i]])
            tabl = "```{}```".format(tabulate(items, headers=["Bonbon", "Quantité"]))
            em = discord.Embed(title="Votre inventaire", description=tabl, color=HALLOWEEN_COLOR())
            em.set_footer(text="Pour en manger un, faîtes ;eat <bonbon>")
            await ctx.send(embed=em)
        else:
            await ctx.send("**Inventaire vide** • Essayez d'avoir des bonbons !")

    @_halloween.command(name="give")
    @commands.guild_only()
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

    @_halloween.command(name="top")
    @commands.guild_only()
    async def _top_hw(self, ctx):
        """Affiche le top global"""
        members = await self.config.all_members(ctx.guild)
        before = []
        for m in members:
            before.append([members[m]["score"], ctx.guild.get_member(m).mention])
        if before:
            after = sorted(before, key=operator.itemgetter(0), reverse=True)
            tabl = "```{}```".format(tabulate(after, headers=["Membre", "Score"]))
            em = discord.Embed(title="Top sur {}".format(ctx.guild.name), description=tabl, color=HALLOWEEN_COLOR(),
                               timestamp=ctx.message.timestamp)
            await ctx.send(embed=em)
        else:
            await ctx.send("Aucun top à afficher")

