# cogs/Template/users.py
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
from database import db
from models import UserInfo

class UserCog(commands.Cog):
    """
    Cog responsible for user management commands and database integration.
    Follows database.py naming conventions.
    """

    def __init__(self, bot):
        self.bot = bot

    # Create a command group for user management
    user_group = SlashCommandGroup("user", "User management commands")
    
            
    @user_group.command(name="add", description="Adds a user to the system")
    async def add_user(
        self, 
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "User to add", required=False, default=None)
    ):
        target_user = user or ctx.author
        
        try:
            # Verificação DEBUG - Verifica o banco de dados diretamente
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE Discord_ID = ?", (target_user.id,))
            raw_data = cursor.fetchone()
            conn.close()
            
            print(f"\n=== DEBUG DATABASE CHECK ===")
            print(f"Raw SQL result: {raw_data}")
            print(f"db.get_user() result: {db.get_user(target_user.id)}")
            
            if raw_data:  # Se existe no banco de dados
                await ctx.respond(
                    f"ℹ️ {target_user.mention} já está no banco de dados (ID: {raw_data['ID']})",
                    ephemeral=True
                )
                return
                
            print(f"\n=== Attempting to add new user ===")
            print(f"User ID: {target_user.id}")
            print(f"Username: {target_user.name}")
            
            # Tentativa de adição com tratamento de erro explícito
            try:
                success = db.add_user(target_user)
            except sqlite3.IntegrityError as e:
                print(f"SQLite IntegrityError: {e}")
                await ctx.respond(
                    f"⚠️ Erro de integridade: {target_user.mention} já existe no banco de dados",
                    ephemeral=True
                )
                return
                
            print(f"Add user result: {success}")
            
            if success:
                # Verificação pós-inserção
                new_user = db.get_user(target_user.id)
                embed = discord.Embed(
                    title="✅ Usuário Adicionado",
                    description=f"{target_user.mention} foi registrado no banco de dados",
                    color=discord.Color.green()
                )
                embed.add_field(name="ID Banco", value=new_user['ID'], inline=True)
                await ctx.respond(embed=embed)
            else:
                await ctx.respond(
                    "❌ Falha ao adicionar usuário. Verifique os logs.",
                    ephemeral=True
                )
                
        except Exception as e:
            print(f"\n=== CRITICAL ERROR ===")
            print(f"Type: {type(e).__name__}")
            print(f"Error: {str(e)}")
            traceback.print_exc()  # Adicione import traceback no topo do arquivo
            
            await ctx.respond(
                "❌ Erro crítico no banco de dados. Contate o administrador.",
                ephemeral=True
            )            
            
            

    @user_group.command(name="delete", description="Removes a user from the system")
    async def delete_user(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "User to remove", required=False, default=None)
    ):
        target_user = user or ctx.author
        
        try:
            # Verificação direta no banco
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE Discord_ID = ?", (target_user.id,))
            exists = cursor.fetchone() is not None
            conn.close()
            
            if not exists:
                await ctx.respond(
                    f"⚠️ {target_user.mention} was not found in the database!",
                    ephemeral=True
                )
                return
                
            if db.delete_user(target_user.id):
                embed = discord.Embed(
                    title="✅ User Removed",
                    description=f"Removed {target_user.mention} from the database.",
                    color=discord.Color.green()
                )
                await ctx.respond(embed=embed)
            else:
                await ctx.respond(
                    f"❌ Failed to remove {target_user.mention} from the database!",
                    ephemeral=True
                )
        except Exception as e:
            await ctx.respond(
                f"❌ Error removing user: {str(e)}",
                ephemeral=True
            )
    @user_group.command(name="update", description="Updates user information")
    async def update_user(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "User to update", required=False, default=None),
        aqw_id: Option(int, "AQW ID (0 to remove)", required=False, default=None),
        aqw_username: Option(str, "AQW Username", required=False, default=None),
        admin: Option(bool, "Admin status", required=False, default=None)
    ):
        """
        Updates user information in the database.

        Args:
            ctx: Command context
            user: Target user (defaults to command author)
            aqw_id: AQW account ID
            aqw_username: AQW account name
            admin: Admin status
        """
        target_user = user or ctx.author
        updates = {}
        
        if aqw_id is not None:
            updates['AQW_ID'] = aqw_id if aqw_id != 0 else 0
        if aqw_username is not None:
            updates['AQW_Username'] = aqw_username
        if admin is not None:
            updates['Admin'] = int(admin)
            
        try:
            if not updates:
                await ctx.respond("⚠️ No fields to update provided!", ephemeral=True)
                return
                
            if db.update_user(target_user.id, **updates):
                embed = discord.Embed(
                    title="✅ User Updated",
                    description=f"Updated {target_user.mention}'s information.",
                    color=discord.Color.green()
                )
                
                if 'AQW_ID' in updates:
                    embed.add_field(name="🎮 AQW ID", value=updates['AQW_ID'], inline=True)
                if 'AQW_Username' in updates:
                    embed.add_field(name="🧙 AQW Username", value=updates['AQW_Username'], inline=True)
                if 'Admin' in updates:
                    embed.add_field(name="👑 Admin Status", value="Yes" if updates['Admin'] else "No", inline=True)
                
                await ctx.respond(embed=embed)
            else:
                await ctx.respond(
                    f"⚠️ {target_user.mention} was not found in the database!",
                    ephemeral=True
                )
        except Exception as e:
            await ctx.respond(
                f"❌ Error updating user: {str(e)}",
                ephemeral=True
            )

    @user_group.command(name="info", description="Displays user information")
    async def user_info(
        self,
        ctx: discord.ApplicationContext,
        user: Option(discord.Member, "User to check", required=False, default=None)
    ):
        """
        Displays detailed user information from the database.

        Args:
            ctx: Command context
            user: Target user (defaults to command author)
        """
        target_user = user or ctx.author
        
        try:
            user_data = db.get_user_info(target_user.id)
            
            if not hasattr(user_data, 'ID'):
                await ctx.respond(
                    f"⚠️ {target_user.mention} is not in the database! Use `/user add` first.",
                    ephemeral=True
                )
                return
                
            embed = discord.Embed(
                title="📋 User Information",
                description=f"Information for {target_user.mention}",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=target_user.display_avatar.url)
            
            # Discord Info
            embed.add_field(name="👤 Display Name", value=user_data.Name, inline=True)
            embed.add_field(name="🆔 Discord ID", value=str(user_data.Discord_ID), inline=True)
            embed.add_field(name="🤖 Is Bot", value="Yes" if user_data.Discord_IsBot else "No", inline=True)
            
            # Account Info
            embed.add_field(name="📅 Account Created", value=user_data.Discord_CreatedAt, inline=True)
            embed.add_field(name="👑 Admin Status", value="Yes" if user_data.Admin else "No", inline=True)
            
            # AQW Info (if available)
            if hasattr(user_data, 'AQW_ID') and user_data.AQW_ID != 0:
                embed.add_field(name="🎮 AQW ID", value=str(user_data.AQW_ID), inline=True)
                embed.add_field(name="🧙 AQW Username", value=user_data.AQW_Username, inline=True)
            
            embed.set_footer(text=f"Database ID: {user_data.ID}")
            
            await ctx.respond(embed=embed)
        except Exception as e:
            await ctx.respond(
                f"❌ Error retrieving user info: {str(e)}",
                ephemeral=True
            )

    @user_group.command(name="list", description="Lists all registered users")
    async def list_users(self, ctx: discord.ApplicationContext):
        """Lists all users in the database."""
        try:
            users = db.list_users()
            
            if not users:
                await ctx.respond("⚠️ No users found in the database!", ephemeral=True)
                return
                
            embed = discord.Embed(
                title="👥 Registered Users",
                color=discord.Color.blurple()
            )
            
            # Split into chunks of 10 users per field
            chunk_size = 10
            user_chunks = [users[i:i + chunk_size] for i in range(0, len(users), chunk_size)]
            
            for i, chunk in enumerate(user_chunks, 1):
                field_value = "\n".join(
                    f"• {u['Discord_Username']} ({u['Discord_ID']})" 
                    for u in chunk
                )
                embed.add_field(
                    name=f"Users {i}",
                    value=field_value,
                    inline=True
                )
                
            embed.set_footer(text=f"Total users: {len(users)}")
            await ctx.respond(embed=embed)
            
        except Exception as e:
            await ctx.respond(
                f"❌ Error listing users: {str(e)}",
                ephemeral=True
            )

def setup(bot):
    bot.add_cog(UserCog(bot))