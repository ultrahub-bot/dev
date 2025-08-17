# bosses.py
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
from database import db

class BossCommands(commands.Cog):
    """Cog para gerenciamento de bosses no banco de dados"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Grupo de comandos slash para /boss
    boss_group = SlashCommandGroup("boss", "Comandos de gerenciamento de bosses")

    # ----------------- ADICIONAR BOSS -----------------
    @boss_group.command(name="add", description="Adiciona um novo boss ao banco de dados")
    @commands.has_permissions(administrator=True)
    async def add_boss(
        self,
        ctx: discord.ApplicationContext,
        name: Option(str, "Nome do boss"),
        party_size: Option(int, "Número de jogadores necessários", default=1),
        map_name: Option(str, "Mapa do boss", default="otto"),
        difficulty: Option(int, "Dificuldade", default=0),
        hp: Option(int, "HP do boss", default=0),
        level: Option(int, "Level do boss", default=0),
        tips: Option(str, "Dicas para o boss", default="Nenhuma"),
        wiki_url: Option(str, "URL da Wiki", default="Wiki_URL"),
        guide_url: Option(str, "URL do guia", default="Guide_URL"),
        thumbnail_url: Option(str, "Thumbnail URL", default="Thumbnail_URL"),
        icon_url: Option(str, "Icon URL", default="Icon_URL"),
        is_hidden: Option(bool, "Boss oculto?", default=False),
        notify_role_id: Option(int, "ID do cargo para notificação", default=0)
    ):
        await ctx.defer(ephemeral=True)

        boss_data = {
            "name": name,
            "party_size": party_size,
            "map": map_name,
            "difficulty": difficulty,
            "hp": hp,
            "level": level,
            "tips": tips,
            "wiki_url": wiki_url,
            "guide_url": guide_url,
            "thumbnail_url": thumbnail_url,
            "icon_url": icon_url,
            "is_hidden": is_hidden,
            "notify_role_id": notify_role_id
        }

        if db.add_boss(boss_data):
            await ctx.followup.send(f"✅ Boss **{name}** adicionado com sucesso!", ephemeral=True)
        else:
            await ctx.followup.send(f"❌ Falha ao adicionar o boss **{name}** (já existe?).", ephemeral=True)

    # ----------------- GET BOSS -----------------
    @boss_group.command(name="get", description="Mostra informações detalhadas de um boss")
    @commands.has_permissions(administrator=True)
    async def get_boss(self, ctx: discord.ApplicationContext, boss_id: Option(int, "ID do boss")):
        await ctx.defer(ephemeral=True)
        boss = db.get_boss(boss_id)
        if not boss:
            return await ctx.followup.send(f"❌ Boss com ID {boss_id} não encontrado!", ephemeral=True)

        embed = discord.Embed(
            title=f"👹 {boss['name']}",
            description=f"Mapa: {boss['map']}\nLevel: {boss['level']} | HP: {boss['hp']} | Dificuldade: {boss['difficulty']}",
            color=discord.Color.green()
        )
        embed.add_field(name="Tamanho do grupo", value=boss['party_size'], inline=True)
        embed.add_field(name="Dicas", value=boss['tips'], inline=False)
        embed.add_field(name="Wiki", value=boss['wiki_url'], inline=True)
        embed.add_field(name="Guia", value=boss['guide_url'], inline=True)
        embed.set_thumbnail(url=boss['thumbnail_url'])
        embed.set_image(url=boss['icon_url'])
        embed.add_field(name="Oculto?", value="✅ Sim" if boss['is_hidden'] else "❌ Não", inline=True)
        if boss['notify_role_id']:
            embed.add_field(name="Cargo de notificação", value=f"<@&{boss['notify_role_id']}>", inline=True)

        await ctx.followup.send(embed=embed, ephemeral=True)



    # ----------------- LISTAR BOSSES -----------------
    @boss_group.command(name="list", description="Lista todos os bosses do banco de dados")
    @commands.has_permissions(administrator=True)
    async def list_bosses(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        bosses = db.list_bosses()

        if not bosses:
            return await ctx.followup.send("ℹ️ Nenhum boss encontrado no banco de dados!", ephemeral=True)

        embed = discord.Embed(title="📋 Lista de Bosses", color=discord.Color.blue())

        for boss in bosses[:25]:  # limite de 25 por embed
            embed.add_field(
                name=f"{boss['name']} (ID: {boss['id']})",
                value=f"Mapa: {boss['map']}\nHP: {boss['hp']} | Level: {boss['level']}\nDificuldade: {boss['difficulty']}",
                inline=False
            )

        if len(bosses) > 25:
            embed.set_footer(text=f"Total de bosses: {len(bosses)} (mostrando os 25 primeiros)")

        await ctx.followup.send(embed=embed, ephemeral=True)

    # ----------------- REMOVER BOSS -----------------
    @boss_group.command(name="delete", description="Remove um boss do banco de dados")
    @commands.has_permissions(administrator=True)
    async def delete_boss(self, ctx: discord.ApplicationContext, boss_id: Option(int, "ID do boss")):
        await ctx.defer(ephemeral=True)
        if db.delete_boss(boss_id):
            await ctx.followup.send(f"✅ Boss com ID {boss_id} removido com sucesso!", ephemeral=True)
        else:
            await ctx.followup.send(f"❌ Boss com ID {boss_id} não encontrado!", ephemeral=True)

    # ----------------- ATUALIZAR BOSS -----------------
    @boss_group.command(name="update", description="Atualiza informações de um boss")
    @commands.has_permissions(administrator=True)
    async def update_boss(
        self,
        ctx: discord.ApplicationContext,
        boss_id: Option(int, "ID do boss"),
        name: Option(str, "Novo nome", required=False, default=None),
        party_size: Option(int, "Número de jogadores", required=False, default=None),
        map_name: Option(str, "Mapa", required=False, default=None),
        difficulty: Option(int, "Dificuldade", required=False, default=None),
        hp: Option(int, "HP", required=False, default=None),
        level: Option(int, "Level", required=False, default=None),
        tips: Option(str, "Dicas", required=False, default=None),
        wiki_url: Option(str, "Wiki URL", required=False, default=None),
        guide_url: Option(str, "Guide URL", required=False, default=None),
        thumbnail_url: Option(str, "Thumbnail URL", required=False, default=None),
        icon_url: Option(str, "Icon URL", required=False, default=None),
        is_hidden: Option(bool, "Boss oculto?", required=False, default=None),
        notify_role_id: Option(int, "ID do cargo para notificação", required=False, default=None)
    ):
        await ctx.defer(ephemeral=True)

        updates = {}
        if name: updates['name'] = name
        if party_size is not None: updates['party_size'] = party_size
        if map_name: updates['map'] = map_name
        if difficulty is not None: updates['difficulty'] = difficulty
        if hp is not None: updates['hp'] = hp
        if level is not None: updates['level'] = level
        if tips: updates['tips'] = tips
        if wiki_url: updates['wiki_url'] = wiki_url
        if guide_url: updates['guide_url'] = guide_url
        if thumbnail_url: updates['thumbnail_url'] = thumbnail_url
        if icon_url: updates['icon_url'] = icon_url
        if is_hidden is not None: updates['is_hidden'] = int(is_hidden)
        if notify_role_id is not None: updates['notify_role_id'] = notify_role_id

        if not updates:
            return await ctx.followup.send("⚠️ Nenhum campo fornecido para atualizar!", ephemeral=True)

        if db.update_boss(boss_id, **updates):
            await ctx.followup.send(f"✅ Boss ID {boss_id} atualizado com sucesso!", ephemeral=True)
        else:
            await ctx.followup.send(f"❌ Falha ao atualizar o boss ID {boss_id}!", ephemeral=True)


def setup(bot):
    bot.add_cog(BossCommands(bot))
