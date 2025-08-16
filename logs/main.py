import discord
from discord.ext import commands
import os
import config
import sys
import re
import json
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config.PREFIX, intents=intents)

def count_active_raids() -> int:
    """Conta o número de raids ativas baseado nos arquivos JSON na pasta de raids"""
    raids_dir = Path("./data/raids")
    if not raids_dir.exists():
        return 0
    return len([f for f in raids_dir.glob("*.json") if f.is_file()])

class BotHandler(FileSystemEventHandler):
    def __init__(self, bot):
        self.bot = bot
        self.ignore_patterns = [
            r'.*/data/.*',       # Ignora toda a pasta data
            r'.*\.json$',        # Ignora todos arquivos JSON
            r'.*\.db$',          # Ignora todos arquivos .db
            r'.*\.sqlite$',      # Ignora arquivos SQLite
            r'.*__pycache__.*'   # Ignora cache Python
        ]
    
    def should_ignore(self, path):
        """Verifica se o arquivo deve ser ignorado"""
        for pattern in self.ignore_patterns:
            if re.fullmatch(pattern, path):
                return True
        return False
    
    def on_modified(self, event):
        if self.should_ignore(event.src_path):
            return
            
        if not event.src_path.endswith('.py'):
            return
        
        print(f"\n🔄 Arquivo de código modificado: {os.path.basename(event.src_path)}")
        self.restart_bot()
    
    def restart_bot(self):
        print("♻️ Reiniciando o bot devido a alterações no código...")
        os.execv(sys.executable, ['python'] + sys.argv)

def load_cogs(bot):
    """Carrega todas as Cogs automaticamente"""
    for root, dirs, files in os.walk('./cogs'):
        for file in files:
            if file.endswith('.py') and file not in ['util.py', 'error.py']:
                relative_path = os.path.relpath(os.path.join(root, file), './cogs')
                module_path = 'cogs.' + relative_path.replace(os.path.sep, '.')[:-3]
                try:
                    bot.load_extension(module_path)
                    print(f"🔧 Módulo carregado: {module_path}")
                except Exception as e:
                    print(f"⚠️ Não foi possível carregar {module_path}: {e}")

@bot.event
async def on_ready():
    # Conta as raids ativas
    active_raids = count_active_raids()
    
    # Configura o status do bot
    activity = discord.Activity(
        name=f"{active_raids} raids ativas | {config.PREFIX}ajuda",
        type=discord.ActivityType.watching
    )
    await bot.change_presence(activity=activity)
    
    print(f"✅ Bot conectado como {bot.user}")
    print(f"📊 Raids ativas: {active_raids}")
    
    # Configura o observador de arquivos
    event_handler = BotHandler(bot)
    observer = Observer()
    
    # Monitora apenas pastas de código
    observer.schedule(event_handler, path='./cogs', recursive=True)
    observer.schedule(event_handler, path='./', recursive=False)  # Para main.py
    
    observer.start()
    print("👀 Monitorando alterações nos arquivos de código (ignorando dados)...")

def run_bot():
    load_cogs(bot)
    bot.run(config.TOKEN)

if __name__ == "__main__":
    run_bot()