# template.py
import discord
from discord.ext import commands
from discord.commands import Option, SlashCommandGroup
from discord.ui import Button, View, Select
from discord import ButtonStyle
from typing import Optional, List, Dict
import json
import asyncio
import os
import random
import aiohttp
# Add this to your UniversalTemplate class in template.py

from database import db
from models import UserInfo

# ============================
# UNIVERSAL DISCORD COG TEMPLATE
# ============================

class UniversalTemplate(commands.Cog):
    """
    Universal Discord Cog Template
    - Supports: Slash commands, groups, buttons, selects, embeds, threads, persistent views.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_dir = "./data/template"
        os.makedirs(self.data_dir, exist_ok=True)
        self.example_file = os.path.join(self.data_dir, "example.json")
        self.ensure_file(self.example_file, {})

        # Example background task
        self.bg_task = self.bot.loop.create_task(self.background_task())

    # ========= FILE UTILITIES =========
    def ensure_file(self, path: str, default_data):
        """Ensures a file exists with default data."""
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=4)

    def load_json(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_json(self, path: str, data: dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    # ========= SLASH COMMAND GROUPS =========
    example_group = SlashCommandGroup("example", "Example commands group")

    @example_group.command(name="ping", description="Check bot latency.")
    async def ping(self, ctx):
        await ctx.respond(f"🏓 Pong! `{round(self.bot.latency * 1000)}ms`")

    @example_group.command(name="echo", description="Echo a message.")
    async def echo(self, ctx, message: Option(str, "Message to echo")):
        await ctx.respond(f"🗣 {message}")

    # ========= AUTOCOMPLETE EXAMPLE =========
    async def autocomplete_fruits(self, ctx: discord.AutocompleteContext):
        fruits = ["Apple", "Banana", "Cherry", "Dragonfruit", "Mango"]
        return [f for f in fruits if ctx.value.lower() in f.lower()]

    @example_group.command(name="fruit", description="Pick a fruit.")
    async def pick_fruit(
        self,
        ctx,
        fruit: Option(str, "Choose a fruit", autocomplete=autocomplete_fruits)
    ):
        await ctx.respond(f"🍓 You picked: {fruit}")

    # ========= COOLDOWN EXAMPLE =========
    @commands.slash_command(name="cooldown", description="Command with cooldown.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def cooldown_test(self, ctx):
        await ctx.respond("✅ This command works, but try again in 10s.")

    # ========= EMBED EXAMPLE =========
    @commands.slash_command(name="embed", description="Send a styled embed.")
    async def embed_example(self, ctx):
        embed = discord.Embed(
            title="Example Embed",
            description="This is a reusable embed template.",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name="Field 1", value="Value 1", inline=True)
        embed.add_field(name="Field 2", value="Value 2", inline=True)
        embed.set_footer(text="Universal Template")
        await ctx.respond(embed=embed)

    # ========= BUTTON EXAMPLE =========
    @commands.slash_command(name="button", description="Show a button.")
    async def button_example(self, ctx):
        view = View()
        view.add_item(Button(label="Click Me", style=ButtonStyle.green, custom_id="example_btn"))
        await ctx.respond("Here is a button:", view=view)

    # ========= SELECT MENU EXAMPLE =========
    @commands.slash_command(name="select", description="Show a select menu.")
    async def select_example(self, ctx):
        view = View()
        select = Select(
            placeholder="Pick something...",
            options=[
                discord.SelectOption(label="Option 1", value="1"),
                discord.SelectOption(label="Option 2", value="2"),
                discord.SelectOption(label="Option 3", value="3")
            ]
        )
        async def select_callback(interaction: discord.Interaction):
            await interaction.response.send_message(f"You picked {select.values[0]}", ephemeral=True)
        select.callback = select_callback
        view.add_item(select)
        await ctx.respond("Here is a select menu:", view=view)


    @commands.slash_command(name="information", description="Get or create user information")
    async def user_info(
        self, 
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "User to check", required=False, default=None)
    ):
        """Shows user information or adds them to database if not found"""
        
        # Use the command author if no user is specified
        target_user = user or ctx.author
        
        # Try to get user from database
        user_data = db.get_user_info(target_user.id)
        
        if not hasattr(user_data, 'ID'):  # If user doesn't exist in database
            # Add user to database with complete info
            db.add_user(target_user)
            
            # Get the newly created user info
            user_data = db.get_user_info(target_user.id)
            
            # Create embed for new user
            embed = discord.Embed(
                title="✅ User Added to Database",
                description=f"Added {target_user.mention} to the database.",
                color=discord.Color.green()
            )
        else:
            # Create embed for existing user
            embed = discord.Embed(
                title="📋 User Information",
                description=f"Information for {target_user.mention}",
                color=discord.Color.blue()
            )
        
        # Add fields with user information
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        # Basic Discord Info
        embed.add_field(name="👤 Display Name", 
                    value=user_data.Name or getattr(target_user, 'display_name', str(target_user)), 
                    inline=True)
        embed.add_field(name="🆔 Discord ID", value=str(user_data.Discord_ID or target_user.id), inline=True)
        embed.add_field(name="🤖 Is Bot", value="Yes" if getattr(user_data, 'Discord_IsBot', target_user.bot) else "No", inline=True)
        
        # Account Info
        created_at = user_data.Discord_CreatedAt or target_user.created_at.strftime("%Y-%m-%d")
        embed.add_field(name="📅 Account Created", value=created_at, inline=True)
        embed.add_field(name="👑 Admin Status", value="Yes" if getattr(user_data, 'Admin', False) else "No", inline=True)
        
        # AQW Info (if available)
        if hasattr(user_data, 'AQW_ID') and user_data.AQW_ID != 0:
            embed.add_field(name="🎮 AQW ID", value=str(user_data.AQW_ID), inline=True)
            embed.add_field(name="🧙 AQW Username", value=user_data.AQW_Username, inline=True)
        
        embed.set_footer(text=f"Database ID: {user_data.ID}")
        
        await ctx.respond(embed=embed)


    # ========= THREAD EXAMPLE =========
    @commands.slash_command(name="thread", description="Create a thread.")
    async def create_thread(self, ctx):
        msg = await ctx.respond("Thread starting...")
        message = await msg.original_response()
        await message.create_thread(name="Example Thread", auto_archive_duration=60)



    # ========= BACKGROUND TASK =========
    async def background_task(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            print("⏳ Background task running...")
            await asyncio.sleep(60)

    # ========= EVENT LISTENER =========
    @commands.Cog.listener()
    async def on_ready(self):
        print(f"✅ Cog '{self.__class__.__name__}' is loaded.")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            if interaction.data.get("custom_id") == "example_btn":
                await interaction.response.send_message("Button clicked!", ephemeral=True)

def setup(bot):
    bot.add_cog(UniversalTemplate(bot))
