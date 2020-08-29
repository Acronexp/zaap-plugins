import asyncio
import logging
import re
from datetime import datetime, timedelta

from redbot.core import Config, commands

log = logging.getLogger("red.zaap-plugins.reverb")

class Reverb(commands.Cog):
    """Assistant personnel"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=736144321857978388, force_registration=True)

        default_user = {}
        default_guild = {}
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

        self.background_loop = None

    async def initialize(self):
        self._enable_bg_loop()

    def _enable_bg_loop(self):
        self.background_loop = self.bot.loop.create_task(self.loop())

        def error_handler(future: asyncio.Future):
            try:
                future.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                log.exception(
                    "Erreur dans la loop de Reverb: ",
                    exc_info=exc,
                )
                asyncio.create_task(
                    self.bot.send_to_owners(
                        "Une erreur important a eu lieue dans la boucle de Reverb.\n"
                        "Aucun rappel ne pourra être envoyé avant d'avoir redémarré le bot.\n"
                        "Consultez les détails dans l'invité de commandes."
                    )
                )
        self.background_loop.add_done_callback(error_handler)

    async def loop(self):
        await self.bot.wait_until_ready()
        while True:
            await self.check_reminders()
            await asyncio.sleep(5)

    def cog_unload(self):
        if self.background_loop:
            self.background_loop.cancel()

    """async def red_delete_data_for_user(self, *, requester, user_id: int):""" # TODO

    def parse_time(self, text: str):
        regex = re.compile(r"(\d*?)\s?([swjdhm])", re.DOTALL | re.IGNORECASE).findall(text)
        now = datetime.now()
        for match in regex:
            if len(match) == 2:
                n, t = int(match[0]), str(match[1]).lower()
                if t in list("swjdhm"):
                    if t in ["s", "w"]:
                        now += timedelta(weeks=n)
                    if t in ["j", "d"]:
                        now += timedelta(days=n)
                    if t == "h":
                        now += timedelta(hours=n)
                    if t == "m":
                        now += timedelta(minutes=n)
                    continue
            raise ValueError("**Le format de temps est invalide.**\n"
                             "Il doit être dans ce format: `Nt` avec `N` le nombre et `t` l'unité de temps\n"
                             "__Exemples :__\n"
                             "- `3j` = 3 jours\n"
                             "- `8h30m` = 8 heures et 30 minutes\n"
                             "- `2w3j9h45m` = 2 semaines, 3 jours, 9 heures et 45 minutes")
        return now

    @commands.group(name="reminder", aliases=["rappel"])
    async def _reminder(self, ctx: commands.Context, when: str, *what):
        """Gestion des rappels."""
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.new, when, what)

    @_reminder.command(usage="<quand> <memo>")
    async def new(self, ctx, when: str, *what):
        what = " ".join(what).strip()
        if len(what) < 2000:
            try:
                time = self.parse_time(when)
            except ValueError:
                try: # On regarde si l'idiot n'aurait pas mis un espace
                    time = self.parse_time(when + what.split()[0])
                    what = " ".join(what.split()[1:])
                except ValueError as e:
                    await ctx.send(e)
                    return
            

