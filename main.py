import discord
from discord.ext import commands
import os
import config
import database
import asyncio
from datetime import datetime

# Configura os intents e o prefixo
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config.PREFIX, intents=intents)

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

def load_cogs(bot):
    """Carrega os módulos (cogs) do bot."""
    cogs = [
        "cogs.template.users",
        "cogs.template.template",
        "cogs.template.bosses",
        "cogs.tasks.welcome",
        "cogs.aqw.vincular",
        "cogs.aqw.charpage",
        "cogs.aqw.servers",
        "cogs.tasks.updatepresence"
    ]

    print("――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――")
    print(" Carregando módulos...")
    print("――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――")
    for cog in cogs:
        try:
            bot.load_extension(cog)
            print(f"✅ Módulo carregado: {cog}")
        except Exception as e:
            print(f"❌ Falha ao carregar {cog}: {e}")

@bot.event
async def on_ready():
    """Executado quando o bot está pronto."""
    print("――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――")
    print(f"✅ Bot conectado como {bot.user} (ID: {bot.user.id})")
    print("――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――")
    print("")
    print("――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――")
    print(" LOGS ")
    print("――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――")
    print(f"Bot iniciado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")      
            
def run_bot():
    """Função principal para iniciar o bot."""
    clear_terminal()
    load_cogs(bot)
    bot.run(config.TOKEN)

if __name__ == "__main__":
    run_bot()
