import discord
from discord.ext import commands
from discord.commands import Option
from typing import Optional

class AFKSystem(commands.Cog):
    """Sistema AFK que gerencia status de ausência dos usuários"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.afk_users = {}  # {user_id: original_nickname}
        
    @commands.slash_command(name="afk", description="Define ou remove seu status AFK")
    async def afk_command(
        self,
        ctx: discord.ApplicationContext,
        reason: Option(str, "Motivo da ausência", required=False, default=None)
    ):
        """Adiciona ou remove o status AFK do usuário"""
        user = ctx.author
        
        # Se o usuário já está AFK
        if user.id in self.afk_users:
            original_nick = self.afk_users[user.id]
            await self.remove_afk(user)
            
            embed = discord.Embed(
                title="✅ Status AFK removido",
                description=f"Bem-vindo de volta, {user.mention}!",
                color=discord.Color.green()
            )
            await ctx.respond(embed=embed)
        else:
            # Salva o nickname original e define o AFK
            self.afk_users[user.id] = user.display_name
            new_nick = f"[AFK] {user.display_name}"[:32]  # Limite de 32 caracteres
            
            try:
                await user.edit(nick=new_nick)
            except discord.Forbidden:
                await ctx.respond("❌ Não tenho permissão para alterar seu apelido.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🛌 Status AFK ativado",
                description=f"{user.mention} está agora ausente." + (f"\n**Motivo:** {reason}" if reason else ""),
                color=discord.Color.orange()
            )
            await ctx.respond(embed=embed)
    
    async def remove_afk(self, user: discord.Member):
        """Remove o status AFK de um usuário"""
        if user.id in self.afk_users:
            original_nick = self.afk_users[user.id]
            
            try:
                await user.edit(nick=original_nick)
            except discord.Forbidden:
                pass  # Ignora se não puder alterar o nickname
            
            del self.afk_users[user.id]
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Remove o status AFK quando o usuário envia uma mensagem"""
        if message.author.id in self.afk_users:
            await self.remove_afk(message.author)
            
            # Envia uma mensagem no canal informando o retorno
            embed = discord.Embed(
                description=f"👋 {message.author.mention} voltou de estar AFK!",
                color=discord.Color.green()
            )
            await message.channel.send(embed=embed, delete_after=10)
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Remove o status AFK quando o usuário entra em um canal de voz"""
        if member.id in self.afk_users and after.channel is not None:
            await self.remove_afk(member)
            
            # Envia uma mensagem no canal informando o retorno
            embed = discord.Embed(
                description=f"🎤 {member.mention} voltou de estar AFK e entrou em um canal de voz!",
                color=discord.Color.green()
            )
            
            # Tenta enviar no canal de voz ou no último canal de texto
            channel = after.channel
            try:
                await channel.send(embed=embed, delete_after=10)
            except:
                # Se não puder enviar no canal de voz, tenta enviar no último canal de texto
                try:
                    if member.dm_channel:
                        await member.dm_channel.send(embed=embed, delete_after=10)
                except:
                    pass
    
    @commands.Cog.listener()
    async def on_ready(self):
        #print(f"✅ Cog '{self.__class__.__name__}' is loaded.")
        pass

def setup(bot):
    bot.add_cog(AFKSystem(bot))