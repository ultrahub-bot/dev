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
        #'cogs.AQW.aqw_charpage',
        #'cogs.AQW.aqw_servers',
        #'cogs.AQW.aqw_vincular',
        #'cogs.AQW.aqw_verificar',
        'cogs.Template.template',
        'cogs.Template.users',
        'cogs.aqw_python.guild'
        #'cogs.Economy.economy',
        #'cogs.Fun.fun',
        #'cogs.Info.Info',
        #'cogs.Insignia.insignia',
        #'cogs.Moderation.mod',
        #'cogs.Moderation.welcome',
        #'cogs.Moderation.verify',        
        #'cogs.Raid.raid',
        #'cogs.Comps.comps',
        #'cogs.Feeds.feeds'
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
    bot.loop.create_task(update_presence())

async def update_presence():
    """Atualiza a presença do bot periodicamente."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            #raid_count = len(bot.get_cog("RaidSystem").active_raids)
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    #name=f"{raid_count} raid(s) ativa(s)",
                    name=f"Hello, I'm {bot.user.name}!",
                    state="Status do servidor",
                    details=f"Atualizado em {datetime.now().strftime('%d/%m %H:%M')}"
                )
            )
            await asyncio.sleep(60)
        except Exception as e:
            print(f"⚠️ Erro ao atualizar presença: {e}")
            await asyncio.sleep(10)

def run_bot():
    """Função principal para iniciar o bot."""
    clear_terminal()  # Limpa o terminal ao iniciar
    load_cogs(bot)
    bot.run(config.TOKEN)

if __name__ == "__main__":
    run_bot()
