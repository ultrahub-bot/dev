import discord
from discord.ext import commands
import os
import config
import database
import asyncio
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.align import Align
from collections import defaultdict, deque

console = Console()
LOG_BUFFER_SIZE = 20  # Número de linhas de log a mostrar
log_buffer = deque(maxlen=LOG_BUFFER_SIZE)

def log(msg):
    log_buffer.append(msg)

# Configura os intents e o prefixo
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config.PREFIX, intents=intents)

# Informações gerais do bot
def get_general_info():
    info = Table.grid(padding=1)
    info.add_column(justify="right", style="bold cyan")
    info.add_column()
    info.add_row("👑 Nome:", f"[bold]{config.BOT_OWNER}[/bold]")
    info.add_row("📧 Contato:", config.BOT_CONTACT)
    info.add_row("🔤 Prefixo:", f"[bold yellow]{config.PREFIX}[/bold yellow]")
    info.add_row("🌐 Servidor:", f"[link={config.BOT_SERVER_URL}]{config.BOT_SERVER_URL}[/link]")
    info.add_row("💾 Backup:", config.BKP_DATA)
    info.add_row("🛡 Raids:", config.RAID_DATA_DIR)
    return Panel(info, title="[bold cyan]Informações Gerais[/bold cyan]", border_style="cyan", padding=(1,2))

def get_cogs_table(loaded_cogs):
    # Agrupa por pasta
    folders = defaultdict(list)
    for cog, status, error in loaded_cogs:
        folder = cog.split('.')[1] if '.' in cog else 'Outros'
        folders[folder].append((cog, status, error))

    table = Table.grid(expand=True)
    for folder, cogs in folders.items():
        subtable = Table(show_header=True, header_style="bold magenta", box=None)
        subtable.add_column("Status", style="bold", width=8)
        subtable.add_column("Módulo", style="dim")
        for cog, status, error in cogs:
            if status:
                subtable.add_row("✅", cog)
            else:
                subtable.add_row("❌", f"{cog} [red]({error})[/red]")
        table.add_row(Panel(subtable, title=f"[bold blue]{folder}[/bold blue]", border_style="blue", padding=(0,1)))
    return Panel(table, title="[bold magenta]Cogs Carregados[/bold magenta]", border_style="magenta", padding=(1,2))

def get_sidebar(loaded_cogs):
    logo = "[bold white on blue] UltraHub Bot [/bold white on blue]"
    general_info = get_general_info()
    cogs_panel = get_cogs_table(loaded_cogs)
    sidebar = Table.grid(padding=1)
    sidebar.add_row(Align.center(logo, vertical="middle"))
    sidebar.add_row(general_info)
    sidebar.add_row(cogs_panel)
    return Panel(sidebar, border_style="bright_blue", padding=(1,2))

def make_layout(loaded_cogs):
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1)
    )
    layout["body"].split_row(
        Layout(name="sidebar", size=50),
        Layout(name="console", ratio=2)
    )
    layout["header"].update(
        Panel("[bold cyan]UltraHub Bot Iniciando...[/bold cyan]", border_style="cyan")
    )
    layout["sidebar"].update(get_sidebar(loaded_cogs))
    logs_text = "\n".join(log_buffer)
    layout["console"].update(
        Panel(logs_text, title="[bold yellow]Console[/bold yellow]", border_style="yellow", padding=(1,2))
    )
    return layout

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

def load_cogs(bot):
    """Carrega os módulos (cogs) do bot e retorna lista de status."""
    cogs = [
        'cogs.Template.template',
        'cogs.Template.users',
        # 'cogs.AQW.aqw_charpage',
        # 'cogs.AQW.aqw_servers',
        # 'cogs.Economy.economy',
        # 'cogs.Fun.fun',
        # 'cogs.Info.Info',
        # 'cogs.Insignia.insignia',
        # 'cogs.Moderation.mod',
        # 'cogs.Moderation.welcome',
        # 'cogs.Moderation.verify',
        # 'cogs.Raid.raid',
        # 'cogs.Comps.comps',
        # 'cogs.Feeds.feeds'
    ]
    loaded_cogs = []
    for cog in cogs:
        try:
            bot.load_extension(cog)
            loaded_cogs.append((cog, True, None))
            log(f"[green]✅ Módulo carregado: {cog}[/green]")
        except Exception as e:
            loaded_cogs.append((cog, False, str(e)))
            log(f"[red]❌ Falha ao carregar {cog}: {e}[/red]")
    return loaded_cogs

async def update_presence():
    """Atualiza a presença do bot periodicamente."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"Hello, I'm {bot.user.name}!",
                    state="Status do servidor",
                    details=f"Atualizado em {datetime.now().strftime('%d/%m %H:%M')}"
                )
            )
            await asyncio.sleep(60)
        except Exception as e:
            log(f"[bold red]⚠️ Erro ao atualizar presença:[/bold red] {e}")
            await asyncio.sleep(10)

@bot.event
async def on_ready():
    """Executado quando o bot está pronto."""
    log(f"[bold green]✅ Bot conectado como [white]{bot.user}[/white] (ID: {bot.user.id})[/bold green]")
    log("[bold yellow]LOGS[/bold yellow]")
    bot.loop.create_task(update_presence())

async def rich_updater(loaded_cogs):
    with Live(make_layout(loaded_cogs), refresh_per_second=4, console=console, screen=True) as live:
        while True:
            live.update(make_layout(loaded_cogs))
            await asyncio.sleep(0.5)

def run_bot():
    """Função principal para iniciar o bot."""
    clear_terminal()
    loaded_cogs = load_cogs(bot)
    log("[bold cyan]UltraHub Bot Iniciando...[/bold cyan]")
    loop = asyncio.get_event_loop()
    loop.create_task(rich_updater(loaded_cogs))
    bot.run(config.TOKEN)

if __name__ == "__main__":
    run_bot()
