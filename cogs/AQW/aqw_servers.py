import discord
from discord.ext import commands
import aiohttp
from datetime import datetime
import pytz
import math

class AQServers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="servers", description="Mostra os servidores online do AQWorlds")
    async def servers(self, ctx: discord.ApplicationContext):
        await ctx.defer()

        async with aiohttp.ClientSession() as session:
            async with session.get("https://game.aq.com/game/api/data/servers") as resp:
                server_data = await resp.json()

        total_players = 0
        online_servers = 0

        # Organizar servidores com informações completas
        servers = []
        for server in server_data:
            count = int(server["iCount"])
            max_players = int(server["iMax"])
            name = server["sName"]
            is_online = server["bOnline"] == 1 or server["bOnline"] == "1"
            status = "🟢" if is_online else "🔴"
            fill = f"{count}/{max_players}"
            servers.append((count, f"{status} {name}: **{fill}**"))

            if is_online:
                total_players += count
                online_servers += 1

        # Ordenar por número de jogadores
        servers.sort(reverse=True)

        # Dividir a lista em duas colunas
        half = math.ceil(len(servers) / 2)
        col1 = "\n".join([s[1] for s in servers[:half]])
        col2 = "\n".join([s[1] for s in servers[half:]])

        # Hora atual no fuso do jogo
        now = datetime.now(pytz.timezone("America/New_York"))
        time_str = now.strftime("%m/%d/%Y %I:%M %p")

        # Embed formatado
        embed = discord.Embed(
            title="🌐 AQW Servers",
            color=discord.Color.dark_purple(),
            description=f"**Server Info**:\n```yaml\nPlayers: {total_players}\nServers: {online_servers} / {len(server_data)}```"
        )
        embed.set_thumbnail(url="https://jix-aqw.github.io/site/logo.png")
        embed.add_field(name="Servidor", value=col1 or "N/A", inline=True)
        embed.add_field(name="Servidor", value=col2 or "N/A", inline=True)
        embed.add_field(name="🕒 Hora", value=f"{time_str} EST", inline=False)

        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(AQServers(bot))
