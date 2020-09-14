import asyncio
import logging
import operator
import os
import random
import time

import discord
from redbot.core import Config, checks, commands
from redbot.core.data_manager import cog_data_path

logger = logging.getLogger("red.zaap-plugins.bettertrivia")

class BetterTrivia(commands.Cog):
    """Testez vos connaissances sur Trivia !"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)
        default_guild = {"default_extensions": [],
                         "scores": {},
                         "insc_timeout": 90,
                         "round_timeout": 30,
                         "max_points": 5,
                         "max_rounds": 30}
        default_global = {"Exts": {}}
        self.config.register_guild(**default_guild)
        self.config.register_guild(**default_global)

        self.exts_path = cog_data_path(self) / "exts"
        self.exts_path.mkdir(exist_ok=True, parents=True)
        self.cache = {}
        self.Extensions = {}

    async def initialize(self):
        self.Extensions = await self.load_extensions()

    def filespaths(self, directory):
        paths = []
        for dirpath, _, filenames in os.walk(directory):
            for f in filenames:
                if f.endswith(".txt"):
                    paths.append(os.path.abspath(os.path.join(dirpath, f)))
        return paths

    async def load_extensions(self):
        exts = {}
        tb = []
        for path in self.filespaths(str(self.exts_path)):
            with open(path, 'r') as ext:
                name = desc = author = lang = exclu = None
                questions = {}
                n = 0
                for l in ext:
                    logger.info(l.rstrip())
                    if "=>" in l:
                        question, reps = [i.strip() for i in l.split("=>", 1)]
                        reps = [r.strip() for r in reps.split(";")]
                        if len(reps) >= 4:
                            good_rep, ex_reps = reps[0], reps[1:]
                            qid = str(n)
                            questions[qid] = {"question": question,
                                            "good_ans": good_rep,
                                            "ex_ans": ex_reps}
                            n += 1

                    elif l.startswith("&NAME="):
                        name = l.split("=", 1)[1]
                        logger.info(f"--NAME = {name}")
                    elif l.startswith("&DESC="):
                        desc = l.split("=", 1)[1]
                        logger.info(f"--DESC = {desc}")
                    elif l.startswith("&AUTHOR="):
                        s_author = l.split("=", 1)[1]
                        if s_author.isdigit():
                            author = int(s_author)
                        else:
                            logger.info(f"Extension path={path} non chargée car auteur invalide")
                            break
                    elif l.startswith("&LANG="):
                        s_lang = l.split("=", 1)[1]
                        if len(s_lang) == 2:
                            lang = s_lang
                        else:
                            logger.info(f"Extension path={path} non chargée car langue invalide")
                            break
                    elif l.startswith("&EXCLU="):
                        s_exclu = l.split("=", 1)[1]
                        exclu = [int(id.strip()) for id in s_exclu.split(";")]

                if all([name, desc, author, lang]) and len(questions) >= 30:
                    id = name.replace(" ", "_").lower()
                    exts[id] = {"name": name,
                                "desc": desc,
                                "author": author,
                                "lang": lang,
                                "exclu": exclu,
                                "content": questions}

                    all_exts = await self.config.Exts()
                    if id not in all_exts:
                        all_exts[id] = {"uses": 0,
                                        "hide": False}
                        await self.config.Exts.set(all_exts)
                    elif all_exts[id]["hide"]:
                        del exts[id]
                        logger.info(f"Extension path={path} non chargée paramètres réglées sur 'hide'")
                        continue
                    tb.append(id)
        logger.info("Extensions trivia chargées : {}".format(", ".join(tb)))
        return exts

    @commands.command()
    @commands.guild_only()
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def trivia(self, ctx, *extensions):
        """Lancer une partie de Trivia"""
        em_color = await ctx.embed_color()
        if not self.Extensions:
            await ctx.send("**Aucune extension disponible** • Contactez le propriétaire du bot pour en proposer.")
            return

        default = bool(extensions)
        if not extensions:
            if await self.config.guild(ctx.guild).default_extensions():
                extensions = await self.config.guild(ctx.guild).default_extensions()
            else:
                await ctx.send("**Aucune extension sélectionnée** • Précisez le nom de extensions (IDs) après la commande, ou configurez des extensions par défaut avec ;triviaset")
                return
        em = discord.Embed(color=em_color, title="Extensions utilisées pour cette partie")
        if default:
            em.set_footer(text="Vous n'avez spécifié aucune extension dans la commande, celles par défaut ont donc été chargées.")

        all_exts = await self.config.Exts()
        questions = {}
        for ext in extensions:
            if ext in self.Extensions:
                if self.Extensions[ext]["exclu"]:
                    if ctx.guild.id not in self.Extensions[ext]["exclu"]:
                        await ctx.send(f"**Extensions invalides** • Vous essayez d'utiliser `{ext}` mais celle-ci est réservée à un ou plusieurs autres serveurs.")
                        return
                name, desc, lang = self.Extensions[ext]["name"], self.Extensions[ext]["desc"], self.Extensions[ext]["lang"].upper()
                author = self.bot.get_user(self.Extensions[ext]["author"])
                em.add_field(name=f"{name} par {author.name}", value=f"*{desc}* [{lang}]", inline=False)

                if ext in all_exts:
                    all_exts[ext]["uses"] += 1

                for q in self.Extensions[ext]["content"]:
                    qid = f"{ext}:{q}"
                    questions[qid] = self.Extensions[ext]["content"][q]
        await self.config.Exts.set(all_exts)

        if questions:
            intro = await ctx.send(embed=em)
            available = list(questions.keys())
            await asyncio.sleep(5)
            await intro.delete(delay=5)
            chanid = ctx.channel.id

            self.cache[chanid] = {"joueurs": {ctx.author.id: 0},
                                  "insc": True,
                                  "reponse": [],
                                  "all_reponses": [],
                                  "round_winner": False,
                                  "tried": []}
            dep_msg = random.choice(["Qui joue ?", "Qui est présent ?", "Qui veut jouer ?",
                                     "Quels sont les participants ?", "Où sont les participants ?",
                                     "Que les joueurs se signalent !"])
            base_em = discord.Embed(color=em_color, title="Trivia » En attente des joueurs...", description=dep_msg)
            jtxt = "\n".join([ctx.guild.get_member(u).mention for u in self.cache[chanid]["joueurs"]])
            em = base_em
            em.add_field(name="Joueurs", value=jtxt)

            msg = await ctx.send(embed=em)
            current = 1
            timeout = time.time() + await self.config.guild(ctx.guild).insc_timeout()
            while len(self.cache[chanid]["joueurs"]) < 8 or time.time() < timeout:
                if len(self.cache[chanid]["joueurs"]) > current:
                    new_em = base_em
                    jtxt = "\n".join([ctx.guild.get_member(u).mention for u in self.cache[chanid]["joueurs"]])
                    new_em.add_field(name="Joueurs", value=jtxt)
                    await msg.edit(embed=new_em)
                    current = len(self.cache[chanid]["joueurs"])
                await asyncio.sleep(2)
            self.cache[chanid]["insc"] = False
            if len(self.cache[chanid]["joueurs"]) >= 2:
                new_em = discord.Embed(color=em_color, title="Trivia » Lancement de la partie...", description="La partie va bientôt démarrer, préparez-vous.")
                jtxt = "\n".join([ctx.guild.get_member(u).mention for u in self.cache[chanid]["joueurs"]])
                new_em.add_field(name="Joueurs", value=jtxt)
                em.set_footer(text="Remportez la partie en gagnant {} manches".format(await self.config.guild(ctx.guild).max_points()))
                await msg.edit(embed=new_em)
                await asyncio.sleep(5)

                async def any_winner():
                    for j in self.cache[chanid]["joueurs"]:
                        if self.cache[chanid]["joueurs"][j] >= await self.config.guild(ctx.guild).max_points():
                            return j
                    return False

                round = 0
                while not await any_winner() or not available or round >= await self.config.guild(ctx.guild).max_rounds():
                    round += 1
                    rand = random.choice(available)
                    available.remove(rand)
                    sample = questions[rand]
                    ans = [sample["good_ans"]] + random.sample(sample["ex_ans"], 3)
                    random.shuffle(ans)
                    good = [str(ans.index(sample["good_ans"]) + 1), sample["good_ans"]]
                    all_ans = dict(map(lambda x: (ans.index(x) + 1, x), ans))

                    em = discord.Embed(title=f"Trivia » Manche #{round}", description=sample["question"], color=em_color)
                    q = await ctx.send(embed=em)
                    await asyncio.sleep(5)

                    reps = ""
                    emoji = [":one:", ":two:", ":three:", ":four:"]
                    for r in all_ans:
                        reps += "{} — **{}**\n".format(emoji[r-1], all_ans[r])
                    self.cache[chanid]["reponse"] = good
                    self.cache[chanid]["all_reponses"] = ans + [1, 2, 3, 4]
                    em.add_field(name="Réponses possibles", value=reps, inline=False)
                    em.set_footer(text="Répondez avec le numéro correspondant à la bonne réponse • Vous n'avez qu'une chance")
                    await q.edit(embed=em)

                    timeout = time.time() + await self.config.guild(ctx.guild).round_timeout()
                    while not self.cache[chanid]["round_winner"] or time.time() < timeout:
                        await asyncio.sleep(0.5)

                    if self.cache[chanid]["round_winner"]:
                        winner = self.cache[chanid]["round_winner"]
                        answer = good[1]
                        rdn = random.choice(["Bravo {winner.mention} ! La réponse était effectivement **{answer}** !",
                                             "Bien joué {winner.mention}, la réponse était **{answer}** !",
                                             "{winner.mention} a gagné cette manche ! La réponse était **{answer}**.",
                                             "La réponse était **{answer}** ! Bravo à {winner.mention} d'avoir trouvé la bonne réponse."])
                        self.cache[chanid]["joueurs"][winner.id] += 1
                        em = discord.Embed(color=0x43b581, description=rdn.format(winner=winner, answer=answer))
                    else:
                        answer = good[1]
                        rdn = random.choice(["Dommage pour vous, la réponse était **{answer}** !",
                                             "La réponse était **{answer}**... Aucun gagnant pour cette manche.",
                                             "C'est un échec ! La réponse était **{answer}**.",
                                             "Oups, c'est loupé. La réponse était **{answer}** !",
                                             "La bonne réponse était **{answer}**... La prochaine fois sera la bonne, peut-être."])
                        em = discord.Embed(color=0xf04747, description=rdn.format(answer=answer))

                    cls = ""
                    top = sorted([[self.cache[chanid]["joueurs"][j], j] for j in self.cache[chanid]["joueurs"]],
                                 key=operator.itemgetter(0))
                    for p in top:
                        user = ctx.guild.get_member(p[1])
                        cls += f"**{p[0]}**pts » {user.mention}\n"
                    em.add_field(name="Classement actuel", value=cls)
                    await ctx.send(embed=em)

                    self.cache[chanid]["reponse"] = []
                    self.cache[chanid]["all_reponses"] = []
                    self.cache[chanid]["round_winner"] = False
                    self.cache[chanid]["tried"] = []
                    await asyncio.sleep(10)
                if round > 1:
                    winner = max([[self.cache[chanid]["joueurs"][j], j] for j in self.cache[chanid]["joueurs"]],
                                     key=operator.itemgetter(0))
                    winner, pts = ctx.guild.get_member(winner[1]), winner[0]
                    scores = await self.config.guild(ctx.guild).scores()
                    if winner.id not in scores:
                        scores[winner.id] = 1
                    else:
                        scores[winner.id] += 1
                    await self.config.guild(ctx.guild).scores.set(scores)
                    em = discord.Embed(title="Trivia » Fin de la partie",
                                       description="Le gagnant est {winner.mention} avec {pts} points !", color=0xFFD700)
                    em.set_footer(text="Consultez le classement global des victoires avec ;triviatop !")
                    await ctx.send(embed=em)
                    del self.cache[chanid]
                else:
                    await ctx.send("**Scores insuffisants** • Trop peu de manches se sont déroulées pour déterminer un vaincqueur.")
            else:
                await ctx.send("**Joueurs insuffisants** • Il doit y avoir au moins 2 joueurs dans la partie.\n"
                               "Astuce : rejoignez une partie en vous signalant au bot lors de l'appel (ex. \"moi\")")
        else:
            await ctx.send("**Aucune extension disponible** • Aucune question n'a pu être chargée. Cela peut être dû à :\n"
                           "- Le chargement d'extensions vides ou invalides\n"
                           "- Le chargement d'extensions réservées à d'autres serveurs (exclusivité)\n"
                           "- Le manque de questions chargées (mini. 30)")

    @commands.command()
    @commands.guild_only()
    async def triviatop(self, ctx):
        """Consulter le classement global sur le serveur"""
        scores = await self.config.guild(ctx.guild).scores()
        txt = ""
        liste = []
        for user in scores:
            try:
                member = ctx.guild.get_member(user)
            except:
                member = self.bot.get_user(user)
            liste.append([scores[user], member])
        top = sorted(liste, key=operator.itemgetter(0), reverse=True)
        for i in top:
            index = top.index(i) + 1
            txt += "**{}**. {}\n".format(index, i[1].name)
        if not txt:
            txt = "**Vide**"
        em = discord.Embed(title="Trivia » Classement du serveur", description=txt, color=await ctx.embed_color())
        await ctx.send(embed=em)

    @commands.group(name="triviaset")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_messages=True)
    async def _triviaset(self, ctx):
        """Paramètres du Trivia"""

    @_triviaset.command()
    async def fermeture(self, ctx, secondes: int = 90):
        """Modifie le nombre de secondes après lesquels l'inscription se ferme

        Minimum = 30s
        Maximum = 300s (5 minutes)
        Défaut = 90s"""
        guild = ctx.guild
        if 300 >= secondes >= 30:
            await self.config.guild(guild).insc_timeout.set(secondes)
            await ctx.send(f"**Délai modifié** • L'inscription expirera après {secondes}s.")
        else:
            await ctx.send(f"**Délai invalide** • Celui-ci doit se situer entre 30 et 300 secondes (5m)")

    @_triviaset.command()
    async def manche(self, ctx, secondes: int = 30):
        """Modifie la longueur (en secondes) des manches

        Minimum = 10s
        Maximum = 90s
        Défaut = 30s"""
        guild = ctx.guild
        if 90 >= secondes >= 10:
            await self.config.guild(guild).round_timeout.set(secondes)
            await ctx.send(f"**Délai modifié** • Les manches se termineront, s'il n'y a pas de gagnant, au bout de {secondes}s.")
        else:
            await ctx.send(f"**Délai invalide** • Celui-ci doit se situer entre 10 et 90 secondes")

    @_triviaset.command()
    async def maxpts(self, ctx, points: int = 5):
        """Modifie le nombre de points à obtenir pour gagner la partie (à condition qu'il y a assez de questions disponibles)

        Minimum = 3
        Maximum = 30
        Défaut = 5"""
        guild = ctx.guild
        if 30 >= points >= 3:
            await self.config.guild(guild).max_points.set(points)
            await ctx.send(f"**Maximum modifié** • Il faudra gagner {points} manches pour remporter la partie.")
        else:
            await ctx.send(f"**Valeur invalide** • Elle doit se situer entre 3 et 30 manches")

    @_triviaset.command()
    async def maxmanches(self, ctx, manches: int = 30):
        """Modifie le maximum de manches qu'il peut y avoir dans une partie

        Minimum = 10
        Maximum = 100
        Défaut = 30"""
        guild = ctx.guild
        if 100 >= manches >= 10:
            await self.config.guild(guild).max_rounds.set(manches)
            await ctx.send(f"**Maximum modifié** • Au bout de {manches} manches, la partie s'arrêtera et désignera le gagnant si personne n'a atteint le max. de points.")
        else:
            await ctx.send(f"**Valeur invalide** • Elle doit se situer entre 10 et 100 manches")

    @_triviaset.group(name="defext", aliases=["extensions"])
    async def _extensions(self, ctx):
        """Gestion des extensions à utiliser par défaut (packs de questions)"""

    @_extensions.command(name="add")
    async def ext_add(self, ctx, ext_id: str):
        """Ajoute une extension à utiliser par défaut"""
        liste = self.Extensions
        if ext_id.lower() in liste:
            ext = liste[ext_id.lower()]
            if ext["exclu"]:
                if ctx.guild.id not in ext["exclu"]:
                    await ctx.send(
                        f"**Exclusivité non respectée** • L'extension {ext_id} est exclusive à un serveur et ne peut être utilisée ici.")
                    return
            exts = await self.config.guild(ctx.guild).default_extensions()
            if ext_id.lower() not in exts:
                exts.append(ext_id.lower())
                await self.config.guild(ctx.guild).default_extensions.set(exts)
                await ctx.send(
                    f"**Extension ajoutée** • L'extension {ext_id} sera chargée par défaut aux prochaines parties.")
            else:
                await ctx.send(
                    f"**Déjà utilisée** • Vous utilisez déjà cette extension dans vos parties."
                )
        else:
            await ctx.send(
                f"**Extension inconnue** • {ext_id} ne semble pas exister. Consultez la liste avec `;triviaset defext list`.")

    @_extensions.command(name="remove")
    async def ext_remove(self, ctx, ext_id: str):
        """Retire une extension à utiliser par défaut"""
        liste = self.Extensions
        if ext_id.lower() in liste:
            exts = await self.config.guild(ctx.guild).default_extensions()
            if ext_id.lower() not in exts:
                exts.remove(ext_id.lower())
                await self.config.guild(ctx.guild).default_extensions.set(exts)
                await ctx.send(
                    f"**Extension retirée** • L'extension {ext_id} ne sera plus chargée par défaut aux prochaines parties.")
            else:
                await ctx.send(
                    f"**Non-utilisée** • Cette extension n'est pas utilisée sur le serveur.")
        else:
            await ctx.send(
                f"**Extension inconnue** • {ext_id} ne semble pas exister. Consultez la liste avec `;triviaset defext list`.")

    @_extensions.command(name="list")
    async def ext_list(self, ctx):
        """Consulter la liste des packs disponibles

        Pour proposer un pack de cartes, contactez Acrone#4424"""
        color = await self.bot.get_embed_color(ctx.channel)
        em = discord.Embed(color=color)
        if self.Extensions:
            for p in self.Extensions:
                ext = self.Extensions[p]
                if ext["exclu"]:
                    if ctx.guild.id not in ext["exclu"]:
                        continue
                total = len(ext["contenu"])
                txt = "**Description** · *{}*\n" \
                      "**Langue** · {}\n" \
                      "**Contenu** · {} questions\n".format(ext["desc"], ext["lang"], total)
                em.add_field(name="{} (ID: {})".format(ext["name"], p), value=txt, inline=False)
            await ctx.send(embed=em)
        else:
            await ctx.send("**Aucune extension disponible** • Consultez le propriétaire du bot pour en proposer.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild:
            channel_id = message.channel.id
            if channel_id in self.cache:
                if self.cache[channel_id]["insc"]:
                    user = message.author
                    if not user.bot:
                        signal = ["me", "moi", "moi!", "moi !", "ici", "oui", "yep", "ouais", "je participe", "je suis là",
                                  "je suis la", "je joue", "présent", "present", "i do", "i am", "go", "allez",
                                  "aller"]
                        if message.content.lower() in signal:
                            if len(self.cache[channel_id]["joueurs"]) < 8:
                                if user.id not in self.cache[channel_id]["joueurs"]:
                                    self.cache[channel_id]["joueurs"][user.id] = 0
                elif message.content in self.cache[channel_id]["all_reponses"]:
                    if message.author.id in self.cache[channel_id]["joueurs"]:
                        if message.author.id not in self.cache[channel_id]["tried"]:
                            if message.content in self.cache[channel_id]["reponse"] and not self.cache[channel_id]["round_winner"]:
                                self.cache[channel_id]["round_winner"] = message.author

    async def save_file(self, msg: discord.Message):
        filename = msg.attachments[0].filename
        file_path = "{}/{}".format(str(self.exts_path), filename)
        await msg.attachments[0].save(file_path)
        self.Extensions = await self.load_extensions()
        return file_path

    @commands.group(name="triviadata")
    @checks.is_owner()
    async def _triviadata(self, ctx):
        """Gestion des fichiers Trivia"""

    @_triviadata.command()
    async def upload(self, ctx, name: str):
        """Charge sur Discord un fichier Trivia"""
        name += ".txt"
        path = self.exts_path / name
        try:
            await ctx.send("Voici votre fichier :", files=[discord.File(path)])
        except:
            await ctx.send("**Fichier introuvable**")

    @_triviadata.command()
    async def download(self, ctx):
        """Télécharge un fichier .txt pour l'inclure dans Trivia"""
        files = ctx.message.attachments
        if files:
            path = await self.save_file(ctx.message)
            await ctx.send("**Fichier sauvegardé** • Chemin = `{}`".format(path))
        else:
            await ctx.send("**Erreur** • Aucun fichier attaché au message")

    @_triviadata.command()
    async def delete(self, ctx, name: str):
        """Supprime un fichier .txt du Trivia"""
        name += ".txt"
        path = self.exts_path / name
        try:
            os.remove(str(path))
            await ctx.send("**Fichier supprimé**")
            await self.load_extensions()
        except Exception as e:
            logger.error(msg=f"Fichier non supprimé ({path})", exc_info=True)
            await ctx.send(f"**Erreur** • Impossible de supprimer le fichier : `{e}`")

    @_triviadata.command()
    async def files(self, ctx):
        """Liste les fichiers dispos pour le Trivia"""
        arr_txt = [x for x in os.listdir(str(self.exts_path)) if x.endswith(".txt")]
        if arr_txt:
            em = discord.Embed(title="Fichiers Trivia disponibles", description="\n".join([f"*{n}*" for n in arr_txt]))
            await ctx.send(embed=em)
        else:
            await ctx.send(f"**Vide** • Aucun fichier n'est disponible")