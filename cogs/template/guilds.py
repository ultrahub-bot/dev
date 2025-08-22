# guilds.py
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
from database import db

class GuildCommands(commands.Cog):
    """Cog para gerenciamento de guildas no banco de dados"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    guild_group = SlashCommandGroup("guild", "Comandos de gerenciamento de guildas")

    @guild_group.command(name="add", description="Adiciona uma nova guilda")
    @commands.has_permissions(administrator=True)
    async def add_guild(
        self,
        ctx: discord.ApplicationContext,
        name: Option(str, "Nome da guilda", required=True),
        leader_id: Option(discord.Member, "Membro líder da guilda", required=True),
        tag: Option(str, "Tag da guilda"),
        motd: Option(str, "Mensagem do dia", required=False, default=""),
        level: Option(int, "Nível inicial", required=False, default=1)
    ):
        await ctx.defer(ephemeral=True)

        guild_data = {
            "name": name,
            "leader_id": leader_id.id,
            "tag": tag,
            "motd": motd,
            "level": level
        }

        if db.add_guild(guild_data):
            await ctx.followup.send(f"✅ Guilda **{name}** adicionada com sucesso!", ephemeral=True)
        else:
            await ctx.followup.send(f"❌ Falha ao adicionar a guilda **{name}**", ephemeral=True)

    @guild_group.command(name="get", description="Mostra informações de uma guilda")
    async def get_guild(self, ctx: discord.ApplicationContext, guild_id: Option(int, "ID da guilda")):
        await ctx.defer(ephemeral=True)
        guild = db.get_guild(guild_id)
        if not guild:
            return await ctx.followup.send(f"❌ Guilda com ID {guild_id} não encontrada!", ephemeral=True)

        embed = discord.Embed(
            title=f"🏰 {guild['name']} [{guild['tag']}]",
            description=f"**Líder:** <@{guild['leader_id']}>\n**Nível:** {guild['level']}",
            color=discord.Color.blue()
        )
        embed.add_field(name="MOTD", value=guild['motd'], inline=False)
        embed.add_field(name="EXP", value=guild['exp'], inline=True)
        embed.add_field(name="Ouro", value=guild['gold'], inline=True)
        embed.add_field(name="Membros", value=f"{guild['capacity']}/{guild['max_capacity']}", inline=True)

        await ctx.followup.send(embed=embed, ephemeral=True)

# ----------------- ATUALIZAR GUILD -----------------
    @guild_group.command(name="update", description="Atualiza informações de uma guild")
    @commands.has_permissions(administrator=True)
    async def update_guild(
        self,
        ctx: discord.ApplicationContext,
        guild_id: Option(int, "ID da guild"),
        leader_id: Option(discord.Member, "Membro líder da guilda", required=True),  # Alterado para discord.Member,
        name: Option(str, "Novo nome", required=True, default=None),
        motd: Option(str, "Nova mensagem do dia", required=False, default=None),
        tag: Option(str, "Nova tag", required=False, default=None),
        level: Option(int, "Novo nível", required=False, default=1),
        exp: Option(int, "Nova experiência", required=False, default=0),
        gold: Option(int, "Novo ouro", required=False, default=0),
        capacity: Option(int, "Nova capacidade", required=False, default=1),
        max_capacity: Option(int, "Nova capacidade máxima", required=False, default=None)
    ):
        await ctx.defer(ephemeral=True)

        updates = {}
        if leader_id is not None: updates['leader_id'] = leader_id.id
        if name: updates['name'] = name
        if motd: updates['motd'] = motd
        if tag: updates['tag'] = tag
        if level is not None: updates['level'] = level
        if exp is not None: updates['exp'] = exp
        if gold is not None: updates['gold'] = gold
        if capacity is not None: updates['capacity'] = capacity
        if max_capacity is not None: updates['max_capacity'] = max_capacity

        if not updates:
            return await ctx.followup.send("⚠️ Nenhum campo fornecido para atualizar!", ephemeral=True)

        if db.update_guild(guild_id, **updates):
            await ctx.followup.send(f"✅ Guild ID {guild_id} atualizada com sucesso!", ephemeral=True)
        else:
            await ctx.followup.send(f"❌ Falha ao atualizar a guild ID {guild_id}!", ephemeral=True)

    @guild_group.command(name="list", description="Lista todas as guildas")
    async def list_guilds(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        guilds = db.list_guilds()

        if not guilds:
            return await ctx.followup.send("ℹ️ Nenhuma guilda encontrada!", ephemeral=True)

        embed = discord.Embed(title="📋 Lista de Guildas", color=discord.Color.blue())

        for guild in guilds[:25]:
            embed.add_field(
                name=f"{guild['name']} [{guild['tag']}] (ID: {guild['id']})",
                value=f"Líder: <@{guild['leader_id']}>\nNível: {guild['level']} | Membros: {guild['capacity']}",
                inline=False
            )

        if len(guilds) > 25:
            embed.set_footer(text=f"Total de guildas: {len(guilds)} (mostrando as 25 primeiras)")

        await ctx.followup.send(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(GuildCommands(bot))