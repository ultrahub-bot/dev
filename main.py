import os
import asyncio
import logging
from datetime import datetime

import discord
from discord.ext import commands

import config
import database  # noqa: F401  # ensure database initializes

# ───────────────────────────────
# Logging configuration
# ───────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

# ───────────────────────────────
# Bot setup
# ───────────────────────────────
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config.PREFIX, intents=intents)

COGS = [
    "cogs.core.admin",
    "cogs.core.help",
    "cogs.core.info",
    "cogs.core.ping",
    "cogs.core.sql",
    "cogs.features.aqw.vincular",
    "cogs.features.aqw.servers",
    "cogs.features.aqw.charpage",
    "cogs.features.fun.afk",
    "cogs.template.users",
    "cogs.template.bosses",
    # "cogs.template.template",
    "cogs.tasks.updatepresence",
    "cogs.events.on_user_join_server",
    # "cogs.events.on_user_leave_server",
]


def clear_terminal() -> None:
    """Clear terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def load_cogs(bot: commands.Bot) -> None:
    """Load bot cogs (extensions)."""
    log.info("Loading cogs...")
    for cog in COGS:
        try:
            bot.load_extension(cog)
            log.info(f"✅ Loaded cog: {cog}")
        except Exception as e:
            log.error(f"❌ Failed to load {cog}: {e}", exc_info=True)


# ───────────────────────────────
# Events
# ───────────────────────────────
@bot.event
async def on_ready() -> None:
    """Runs when the bot is ready."""
    log.info("――――――――――――――――――――――――――――――――――――――――――")
    log.info(f"✅ Bot connected as {bot.user} (ID: {bot.user.id})")
    log.info("――――――――――――――――――――――――――――――――――――――――――")



# ───────────────────────────────
# Background tasks
# ───────────────────────────────
async def funny() -> None:
    pass

# ───────────────────────────────
# Entrypoint
# ───────────────────────────────
def run_bot() -> None:
    """Main function to run the bot."""
    clear_terminal()
    load_cogs(bot)
    bot.run(config.TOKEN)


if __name__ == "__main__":
    run_bot()
