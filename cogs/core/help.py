import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
from discord import Embed, Color

class Help(commands.Cog):
    """Help commands for the bot"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    help_group = SlashCommandGroup("help", "Help commands")

    @help_group.command(name="commands", description="List all available commands")
    async def commands(self, ctx: discord.ApplicationContext):
        """Lists all available commands"""
        embed = Embed(
            title="🤖 Bot Commands",
            description="Here are all the available commands:",
            color=Color.blurple()
        )
        
        # Get all cogs and their commands
        for cog_name in self.bot.cogs:
            cog = self.bot.get_cog(cog_name)
            commands_list = cog.get_commands()
            
            if commands_list:
                value = "\n".join(f"`/{cmd.name}` - {cmd.description}" for cmd in commands_list)
                embed.add_field(name=cog_name, value=value, inline=False)
        
        embed.set_footer(text="Use /help [command] for more info on a specific command")
        await ctx.respond(embed=embed)

    @help_group.command(name="about", description="Information about the bot")
    async def about(self, ctx: discord.ApplicationContext):
        """Shows information about the bot"""
        embed = Embed(
            title="ℹ️ Sobre",
            color=Color.blurple()
        )
        embed.add_field(name="Creator", value="Marcel Pineoak", inline=True)
        embed.add_field(name="Version", value="1.0.0", inline=True)
        embed.add_field(name="Library", value=f"pycord.py {discord.__version__}", inline=True)
        embed.add_field(name="Source Code", value="[GitHub Repo](https://github.com/your/repo)", inline=False)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(Help(bot))