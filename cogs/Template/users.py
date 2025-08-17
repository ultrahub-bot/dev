# users.py
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
from database import db
from models import UserInfo

class UserCommands(commands.Cog):
    """Cog para gerenciamento de usuários no banco de dados"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Cria um grupo de comandos slash para /user
    user_group = SlashCommandGroup("user", "Comandos de gerenciamento de usuários")

    # =============================================
    # COMANDOS DE ADMINISTRAÇÃO DE USUÁRIOS
    # =============================================

    @user_group.command(name="add", description="Adiciona um usuário ao banco de dados")
    @commands.has_permissions(administrator=True)
    async def add_user(
        self, 
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Membro para adicionar", required=False, default=None)
    ):
        target = member or ctx.author
        
        # Verificação adicional no comando
        if db.check_user_exists(target.id):
            return await ctx.respond(f"❌ {target.mention} já está cadastrado (ID: {target.id})", ephemeral=True)
        
        if db.add_user(target):
            await ctx.respond(f"✅ {target.mention} foi cadastrado com sucesso!", ephemeral=True)
        else:
            await ctx.respond(f"❌ Falha ao cadastrar {target.mention}", ephemeral=True)        

    @user_group.command(name="delete", description="Remove um usuário do banco de dados")
    @commands.has_permissions(administrator=True)
    async def delete_user(
        self, 
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Membro para remover", required=False, default=None)
    ):
        """Remove um usuário do banco de dados"""
        
        # Usa o autor se nenhum membro for especificado
        target = member or ctx.author
        
        try:
            # Tenta remover o usuário
            success = db.delete_user(target.id)
            
            if success:
                await ctx.respond(f"✅ {target.mention} foi removido do banco de dados!", ephemeral=True)
            else:
                await ctx.respond(f"⚠️ {target.mention} não foi encontrado no banco de dados!", ephemeral=True)
                
        except Exception as e:
            await ctx.respond(f"❌ Erro ao remover usuário: {e}", ephemeral=True)




    @user_group.command(name="update", description="Atualiza informações do usuário")
    @commands.has_permissions(administrator=True)
    async def update_user(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "Usuário para atualizar", required=False, default=None),
        aqw_id: Option(int, "ID do AQW (0 para remover)", required=False, default=None),
        aqw_username: Option(str, "Nome de usuário do AQW", required=False, default=None),
        admin: Option(bool, "Status de admin", required=False, default=None)
    ):
        """Atualiza informações de um usuário no banco de dados"""
        target = user or ctx.author
        await ctx.defer(ephemeral=True)
        
        # Verifica se o usuário existe no banco
        if not db.get_user(target.id):
            return await ctx.followup.send(
                f"⚠️ {target.mention} não está cadastrado no banco de dados!",
                ephemeral=True
            )
        
        # Prepara as atualizações
        updates = {}
        if aqw_id is not None:
            updates['aqw_id'] = aqw_id
        if aqw_username is not None:
            updates['aqw_username'] = aqw_username
        if admin is not None:
            updates['admin'] = int(admin)
        
        # Verifica se há campos para atualizar
        if not updates:
            return await ctx.followup.send(
                "⚠️ Nenhum campo para atualizar foi fornecido!",
                ephemeral=True
            )
        
        # Tenta atualizar
        try:
            success = db.update_user(target.id, **updates)
            if not success:
                raise Exception("Falha ao atualizar usuário")
            
            # Cria embed de resposta
            embed = discord.Embed(
                title="✅ Atualização Concluída",
                description=f"Dados de {target.mention} foram atualizados",
                color=discord.Color.green()
            )
            
            if 'AQW_ID' in updates:
                embed.add_field(name="ID AQW", value=updates['aqw_id'], inline=True)
            if 'AQW_Username' in updates:
                embed.add_field(name="Usuário AQW", value=updates['aqw_username'], inline=True)
            if 'Admin' in updates:
                embed.add_field(name="Admin", value="✅ Sim" if updates['admin'] else "❌ Não", inline=True)
            
            await ctx.followup.send(embed=embed)
            
        except Exception as e:
            await ctx.followup.send(
                f"❌ Erro ao atualizar usuário: {str(e)}",
                ephemeral=True
            )



    @user_group.command(name="list", description="Lista todos os usuários no banco de dados")
    @commands.has_permissions(administrator=True)
    async def list_users(self, ctx: discord.ApplicationContext):
        """Lista todos os usuários no banco de dados"""
        
        try:
            # Obtém todos os usuários
            users = db.list_users()
            
            if not users:
                await ctx.respond("ℹ️ Nenhum usuário encontrado no banco de dados!", ephemeral=True)
                return
                
            # Cria um embed com a lista de usuários
            embed = discord.Embed(
                title="📋 Usuários no Banco de Dados",
                color=discord.Color.blue()
            )
            
            # Adiciona até 25 usuários (limite do Discord)
            for user in users[:25]:
                embed.add_field(
                    name=f"ID: {user['ID']} - {user['Name']}",
                    value=f"Discord ID: {user['discord_id']}\nAdmin: {'✅' if user['admin'] else '❌'}",
                    inline=True
                )
            
            # Adiciona contagem total se houver mais de 25
            if len(users) > 25:
                embed.set_footer(text=f"Total de usuários: {len(users)} (mostrando os 25 primeiros)")
            
            await ctx.respond(embed=embed, ephemeral=True)
            
        except Exception as e:
            await ctx.respond(f"❌ Erro ao listar usuários: {e}", ephemeral=True)

    @user_group.command(name="get", description="Obtém informações de um usuário")
    @commands.has_permissions(administrator=True)
    async def get_user(
        self, 
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Membro para consultar", required=False, default=None)
    ):
        """Obtém informações detalhadas de um usuário"""
        
        # Usa o autor se nenhum membro for especificado
        target = member or ctx.author
        
        try:
            # Obtém as informações do usuário como objeto UserInfo
            user_info = db.get_user_info(target.id)
            
            # Verifica se o usuário existe
            if not hasattr(user_info, 'id'):
                await ctx.respond(f"⚠️ {target.mention} não foi encontrado no banco de dados!", ephemeral=True)
                return
                
            # Cria um embed com as informações
            embed = discord.Embed(
                title=f"📋 Informações de {user_info.name}",
                color=discord.Color.green()
            )
            
            embed.set_thumbnail(url=target.display_avatar.url)
            
            # Adiciona campos básicos
            embed.add_field(name="🆔 ID do Banco", value=user_info.id, inline=True)
            embed.add_field(name="👤 Nome", value=user_info.name, inline=True)
            embed.add_field(name="🤖 É Bot", value="✅" if user_info.discord_is_bot else "❌", inline=True)
            
            # Adiciona informações do Discord
            embed.add_field(name="📅 Criado em", value=user_info.discord_created_at, inline=True)
            embed.add_field(name="👑 Admin", value="✅" if user_info.is_admin else "❌", inline=True)
            
            # Adiciona informações do AQW se existirem
            if hasattr(user_info, 'aqw_id') and user_info.aqw_id != 0:
                embed.add_field(name="🎮 AQW ID", value=user_info.aqw_id, inline=True)
                embed.add_field(name="🧙 AQW Username", value=user_info.aqw_username, inline=True)
            
            await ctx.respond(embed=embed, ephemeral=True)
            
        except Exception as e:
            await ctx.respond(f"❌ Erro ao obter informações do usuário: {e}", ephemeral=True)

def setup(bot):
    bot.add_cog(UserCommands(bot))