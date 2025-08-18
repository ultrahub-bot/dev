import discord
from discord.ext import commands
from discord.commands import Option, SlashCommandGroup
from discord import Embed, Color

class Admin(commands.Cog):
    """Administrative commands for server management"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    admin_group = SlashCommandGroup("admin", "Administrative commands")

    @admin_group.command(name="kick", description="Kick a member from the server")
    @commands.has_permissions(kick_members=True)
    async def kick(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Member to kick"),
        reason: Option(str, "Reason for kick", required=False, default="No reason provided")
    ):
        """Kicks a member from the server"""
        try:
            await member.kick(reason=reason)
            embed = Embed(
                title="✅ Member Kicked",
                description=f"{member.mention} has been kicked by {ctx.author.mention}",
                color=Color.green()
            )
            embed.add_field(name="Reason", value=reason)
            await ctx.respond(embed=embed)
        except Exception as e:
            await ctx.respond(f"❌ Failed to kick member: {e}", ephemeral=True)

    @admin_group.command(name="ban", description="Ban a member from the server")
    @commands.has_permissions(ban_members=True)
    async def ban(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Member to ban"),
        reason: Option(str, "Reason for ban", required=False, default="No reason provided")
    ):
        """Bans a member from the server"""
        try:
            await member.ban(reason=reason)
            embed = Embed(
                title="✅ Member Banned",
                description=f"{member.mention} has been banned by {ctx.author.mention}",
                color=Color.green()
            )
            embed.add_field(name="Reason", value=reason)
            await ctx.respond(embed=embed)
        except Exception as e:
            await ctx.respond(f"❌ Failed to ban member: {e}", ephemeral=True)

    @admin_group.command(name="purge", description="Delete multiple messages")
    @commands.has_permissions(manage_messages=True)
    async def purge(
        self,
        ctx: discord.ApplicationContext,
        amount: Option(int, "Number of messages to delete", min_value=1, max_value=100)
    ):
        """Purges a specified number of messages"""
        try:
            await ctx.channel.purge(limit=amount + 1)  # +1 to include the command message
            msg = await ctx.respond(f"🧹 Deleted {amount} messages", ephemeral=True)
            await asyncio.sleep(3)
            await msg.delete()
        except Exception as e:
            await ctx.respond(f"❌ Failed to purge messages: {e}", ephemeral=True)

def setup(bot):
    bot.add_cog(Admin(bot))