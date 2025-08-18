import discord
from discord.ext import commands
from discord import Embed, Color
import time

class Ping(commands.Cog):
    """Ping commands to check bot latency"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    @commands.slash_command(name="ping", description="Check bot latency")
    async def ping(self, ctx: discord.ApplicationContext):
        """Checks the bot's latency to Discord"""
        # Measure time for response
        start_time = time.time()
        message = await ctx.respond("🏓 Pinging...")
        end_time = time.time()
        
        # Calculate different ping types
        websocket_ping = round(self.bot.latency * 1000)
        response_ping = round((end_time - start_time) * 1000)
        
        embed = Embed(
            title="🏓 Pong!",
            color=Color.green()
        )
        embed.add_field(name="WebSocket", value=f"{websocket_ping}ms", inline=True)
        embed.add_field(name="Response", value=f"{response_ping}ms", inline=True)
        
        await message.edit_original_response(content=None, embed=embed)

    @commands.slash_command(name="status", description="Check bot status")
    async def status(self, ctx: discord.ApplicationContext):
        """Checks the bot's overall status"""
        embed = Embed(
            title="🤖 Bot Status",
            color=Color.green()
        )
        
        # System status
        embed.add_field(name="🟢 Online", value="Bot is online and responsive", inline=False)
        embed.add_field(name="🏓 Ping", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="🏠 Servers", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="👥 Users", value=sum(g.member_count for g in self.bot.guilds), inline=True)
        
        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(Ping(bot))