import discord
from discord.ext import commands
from discord.commands import slash_command, SlashCommandGroup
from discord.commands import Option
import datetime
import json


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.moderator_role_id = 1361379753503883516  # ID do cargo de moderador

    async def is_moderator(self, ctx):
        moderator_role = ctx.guild.get_role(self.moderator_role_id)
        return moderator_role in ctx.author.roles

    # Grupo principal de moderação com descrição
    mod = SlashCommandGroup(
        "mod", 
        "Comandos de moderação para administração do servidor", 
        guild_ids=[1361196873045643344]
    )

    @mod.command(description="Limpa uma quantidade específica de mensagens no canal")
    async def clear(self, ctx, amount: Option(int, "Número de mensagens para limpar", min_value=1, max_value=100)):
        if not await self.is_moderator(ctx):
            return await ctx.respond("❌ Você não tem permissão para usar este comando.", ephemeral=True)
            
        await ctx.defer(ephemeral=True)
        await ctx.channel.purge(limit=amount + 1)  # +1 para incluir o próprio comando
        await ctx.respond(f"✅ {amount} mensagens foram limpas com sucesso.", ephemeral=True)

    @mod.command(description="Expulsa um membro do servidor")
    async def kick(self, ctx, member: Option(discord.Member, "Membro a ser expulso")):
        if not await self.is_moderator(ctx):
            return await ctx.respond("❌ Você não tem permissão para usar este comando.", ephemeral=True)
            
        if ctx.author.top_role <= member.top_role:
            return await ctx.respond("❌ Você não pode expulsar alguém com cargo igual ou superior ao seu.", ephemeral=True)
            
        await member.kick()
        await ctx.respond(f"✅ {member.display_name} foi expulso com sucesso.", ephemeral=True)

    @mod.command(description="Bane um membro do servidor")
    async def ban(self, ctx, member: Option(discord.Member, "Membro a ser banido")):
        if not await self.is_moderator(ctx):
            return await ctx.respond("❌ Você não tem permissão para usar este comando.", ephemeral=True)
            
        if ctx.author.top_role <= member.top_role:
            return await ctx.respond("❌ Você não pode banir alguém com cargo igual ou superior ao seu.", ephemeral=True)
            
        await member.ban(delete_message_days=0)
        await ctx.respond(f"✅ {member.display_name} foi banido com sucesso.", ephemeral=True)

    @mod.command(description="Silencia um membro (adiciona o cargo de mute)")
    async def mute(self, ctx, member: Option(discord.Member, "Membro a ser silenciado")):
        if not await self.is_moderator(ctx):
            return await ctx.respond("❌ Você não tem permissão para usar este comando.", ephemeral=True)
            
        muted_role = ctx.guild.get_role(1361877076306825328)  # SUBSTITUA pelo ID real do cargo de mute
        if not muted_role:
            return await ctx.respond("❌ Cargo de mute não está configurado corretamente.", ephemeral=True)
            
        await member.add_roles(muted_role)
        await ctx.respond(f"✅ {member.display_name} foi silenciado com sucesso.", ephemeral=True)

    @mod.command(description="Remove o silêncio de um membro (remove o cargo de mute)")
    async def unmute(self, ctx, member: Option(discord.Member, "Membro a ser dessilenciado")):
        if not await self.is_moderator(ctx):
            return await ctx.respond("❌ Você não tem permissão para usar este comando.", ephemeral=True)
            
        muted_role = ctx.guild.get_role(1361877076306825328)  # SUBSTITUA pelo ID real do cargo de mute
        if not muted_role:
            return await ctx.respond("❌ Cargo de mute não está configurado corretamente.", ephemeral=True)
            
        await member.remove_roles(muted_role)
        await ctx.respond(f"✅ {member.display_name} foi dessilenciado com sucesso.", ephemeral=True)

    @mod.command(description="Aplica um timeout temporário a um membro")
    async def timeout(self, ctx, 
                     member: Option(discord.Member, "Membro a ser punido"),
                     minutes: Option(int, "Duração em minutos (máx. 40320)", min_value=1, max_value=40320)):
        if not await self.is_moderator(ctx):
            return await ctx.respond("❌ Você não tem permissão para usar este comando.", ephemeral=True)
            
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout_for(duration)
        await ctx.respond(f"✅ {member.display_name} foi punido por {minutes} minutos.", ephemeral=True)

    @mod.command(description="Mostra o número de advertências de um membro")
    async def warnings(self, ctx, member: Option(discord.Member, "Membro para ver advertências")):
        await self.open_account(member)
        users = await self.get_user_data()
        warns = users[str(member.id)]["warns"]
        await ctx.respond(f"ℹ️ {member.display_name} tem {warns} advertências.", ephemeral=True)

    @mod.command(description="Adverte um membro (adiciona um warn ao histórico)")
    async def warn(self, ctx, member: Option(discord.Member, "Membro a ser advertido")):
        if not await self.is_moderator(ctx):
            return await ctx.respond("❌ Você não tem permissão para usar este comando.", ephemeral=True)
            
        await self.open_account(member)
        warns = await self.update_warns(member)
        await ctx.respond(f"⚠️ {member.display_name} foi advertido. Total de advertências: {warns}.", ephemeral=True)

    async def open_account(self, user):
        try:
            with open("./Cogs/Moderation/reports.json", "r") as f:
                users = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            users = {}

        if str(user.id) not in users:
            users[str(user.id)] = {"warns": 0}
            with open("./Cogs/Moderation/reports.json", "w") as f:
                json.dump(users, f, indent=4)

    async def get_user_data(self):
        try:
            with open("./Cogs/Moderation/reports.json", "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    async def update_warns(self, user, change=1):
        users = await self.get_user_data()
        user_id = str(user.id)
        
        if user_id not in users:
            users[user_id] = {"warns": 0}
            
        users[user_id]["warns"] += change
        
        with open("./Cogs/Moderation/reports.json", "w") as f:
            json.dump(users, f, indent=4)
            
        return users[user_id]["warns"]

def setup(bot):
    bot.add_cog(Moderation(bot))