import discord
from discord.ext import commands
from discord.commands import Option, SlashCommandGroup
from discord import Embed, Color
from datetime import datetime

class Info(commands.Cog):
    """Information commands about server and users"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    info_group = SlashCommandGroup("info", "Information commands")

    @info_group.command(name="server", description="Show server information")
    async def server_info(self, ctx: discord.ApplicationContext):
        """Shows information about the current server"""
        guild = ctx.guild
        
        embed = Embed(
            title=f"🖥️ {guild.name}",
            color=Color.blue()
        )
        
        # Basic server info
        embed.add_field(name="🆔 Server ID", value=guild.id, inline=True)
        embed.add_field(name="👑 Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="📅 Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        
        # Member stats
        online = sum(member.status != discord.Status.offline for member in guild.members)
        embed.add_field(name="👥 Members", value=f"Total: {guild.member_count}\nOnline: {online}", inline=True)
        
        # Channel stats
        text = len(guild.text_channels)
        voice = len(guild.voice_channels)
        embed.add_field(name="📚 Channels", value=f"Text: {text}\nVoice: {voice}", inline=True)
        
        # Other info
        embed.add_field(name="🚀 Boosts", value=guild.premium_subscription_count, inline=True)
        embed.add_field(name="✨ Boost Level", value=guild.premium_tier, inline=True)
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        await ctx.respond(embed=embed)

    @info_group.command(name="user", description="Show user information")
    async def user_info(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "User to check", required=False, default=None)
    ):
        """Shows information about a user"""
        target = user or ctx.author
        
        embed = Embed(
            title=f"👤 {target.display_name}",
            color=target.color if target.color != Color.default() else Color.blue()
        )
        
        # Basic user info
        embed.add_field(name="🆔 User ID", value=target.id, inline=True)
        embed.add_field(name="🤖 Is Bot", value="Yes" if target.bot else "No", inline=True)
        embed.add_field(name="📅 Account Created", value=target.created_at.strftime("%Y-%m-%d"), inline=True)
        
        # Server-specific info
        if isinstance(target, discord.Member):
            embed.add_field(name="🎭 Nickname", value=target.nick or "None", inline=True)
            embed.add_field(name="🎭 Joined Server", value=target.joined_at.strftime("%Y-%m-%d"), inline=True)
            embed.add_field(name="🎭 Top Role", value=target.top_role.mention, inline=True)
        
        embed.set_thumbnail(url=target.display_avatar.url)
        
        await ctx.respond(embed=embed)

    @info_group.command(name="bot", description="Show bot information")
    async def bot_info(self, ctx: discord.ApplicationContext):
        """Shows information about the bot"""
        embed = Embed(
            title=f"🤖 {self.bot.user.name}",
            description=self.bot.description or "A helpful Discord bot",
            color=Color.blurple()
        )
        
        # Bot stats
        embed.add_field(name="🆔 Bot ID", value=self.bot.user.id, inline=True)
        embed.add_field(name="📅 Created", value=self.bot.user.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="🏠 Servers", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="⚡ Ping", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(Info(bot))