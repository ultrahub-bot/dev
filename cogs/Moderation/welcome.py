# cogs/Moderation/welcome.py
import discord
from discord.ext import commands
import config

class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # IDs importantes do config
        self.pending_role_id = config.PENDING_ROLE_ID
        self.welcome_channel_id = config.WELCOME_CHANNEL_ID 
        self.rules_channel_id = config.RULES_CHANNEL_ID
        self.verify_channel_id = config.VERIFY_CHANNEL_ID
        self.notabot_role_id = config.NOTABOT_ROLE_ID   
        self.bot.loop.create_task(self.initialize_pending_members())

    async def initialize_pending_members(self):
        """Verifica todos os membros ao iniciar o bot"""
        await self.bot.wait_until_ready()
        guild = self.bot.guilds[0]
        pending_role = guild.get_role(self.pending_role_id)
        notabot_role = guild.get_role(self.notabot_role_id)  # Adicionado

        if not pending_role or not notabot_role:  # Verifica ambos os cargos
            print(f"[ERRO] Cargos não encontrados (Pending: {self.pending_role_id}, NotABot: {self.notabot_role_id})")
            return

        for member in guild.members:
            # Verifica se o membro NÃO possui AMBOS os cargos
            if pending_role not in member.roles and notabot_role not in member.roles:
                await self.process_member(member)

    async def process_member(self, member: discord.Member):
        guild = member.guild
        pending_role = guild.get_role(self.pending_role_id)
        notabot_role = guild.get_role(self.notabot_role_id)

        # Verificação redundante para segurança
        if notabot_role in member.roles:
            print(f"[INFO] {member} já possui NotABot. Ignorando.")
            return

        try:
            await member.add_roles(pending_role, reason="Processamento pós-inicialização")
            print(f"[CARGO] Pending adicionado a {member}")
        except Exception as e:
            print(f"[ERRO] Falha ao adicionar cargo: {e}")
            return

        # Envia as mensagens de boas-vindas
        welcome_channel = guild.get_channel(self.welcome_channel_id)
        verify_channel = guild.get_channel(self.verify_channel_id)
        rules_channel = guild.get_channel(self.rules_channel_id)

        if all([welcome_channel, verify_channel, rules_channel]):
            try:
                embed = self.create_welcome_embed(member, verify_channel, rules_channel)
                await welcome_channel.send(embed=embed)
            except Exception as e:
                print(f"[ERRO] Ao enviar embed público para {member}: {e}")

            try:
                embed_dm = self.create_dm_embed(member, verify_channel, rules_channel)
                await member.send(embed=embed_dm)
            except discord.Forbidden:
                print(f"[AVISO] {member} bloqueou DMs.")
            except Exception as e:
                print(f"[ERRO DM] {e}")

    def create_welcome_embed(self, member: discord.Member, verify_channel: discord.TextChannel, rules_channel: discord.TextChannel) -> discord.Embed:
        embed = discord.Embed(
            title="🎉 Welcome | Bem-vindo(a)!",
            description=(
                f"👤 {member.mention}, we're happy to have you here!\n"
                f"👤 Estamos felizes em te receber no servidor!"
            ),
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="🔐 Verification | Verificação",
            value=(
                f"👉 Please verify yourself in {verify_channel.mention}\n"
                f"👉 Verifique-se em {verify_channel.mention} para liberar os canais"
            ),
            inline=False
        )
        embed.add_field(
            name="📜 Rules | Regras",
            value=(
                f"📖 Read the rules in {rules_channel.mention}\n"
                f"📖 Leia as regras em {rules_channel.mention}"
            ),
            inline=False
        )
        embed.set_footer(text="Enjoy your stay | Aproveite sua estadia!", icon_url=member.display_avatar.url)
        return embed

    def create_dm_embed(self, member: discord.Member, verify_channel: discord.TextChannel, rules_channel: discord.TextChannel) -> discord.Embed:
        embed = discord.Embed(
            title="👋 Welcome Message | Mensagem de Boas-vindas",
            description=(
                f"Hello {member.name}, welcome to our community!\n"
                f"Olá {member.name}, bem-vindo(a) à nossa comunidade!"
            ),
            color=discord.Color.green()
        )
        embed.add_field(
            name="✅ Start Here | Comece Aqui",
            value=(
                f"• {verify_channel.mention} → Verify to unlock channels\n"
                f"• {verify_channel.mention} → Verifique-se para liberar os canais"
            ),
            inline=False
        )
        embed.add_field(
            name="📖 Rules | Regras",
            value=(
                f"{rules_channel.mention} → Read and follow the rules\n"
                f"{rules_channel.mention} → Leia e siga as regras"
            ),
            inline=False
        )
        embed.set_footer(text="Need help? Ask the staff! | Precisa de ajuda? Fale com a equipe.")
        return embed

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        pending_role = guild.get_role(self.pending_role_id)
        notabot_role = guild.get_role(self.notabot_role_id)  # Adicionado

        # Verifica se o membro já é verificado
        if notabot_role in member.roles:
            print(f"[INFO] {member} já possui NotABot. Ignorando.")
            return

        if pending_role:
            try:
                await member.add_roles(pending_role, reason="Novo membro - verificação pendente")
                print(f"[CARGO] Pending adicionado a {member}")
            except Exception as e:
                print(f"[ERRO] Falha ao adicionar cargo: {e}")
        else:
            print(f"[ERRO] Cargo não encontrado (ID: {self.pending_role_id})")

        # Buscar canais
        welcome_channel = guild.get_channel(self.welcome_channel_id)
        verify_channel = guild.get_channel(self.verify_channel_id)
        rules_channel = guild.get_channel(self.rules_channel_id)

        # Garantir que todos os canais estão disponíveis
        if not all([welcome_channel, verify_channel, rules_channel]):
            print("[ERRO] Um ou mais canais não encontrados!")
            return

        # Enviar mensagem de boas-vindas pública com embed
        try:
            embed = self.create_welcome_embed(member, verify_channel, rules_channel)
            await welcome_channel.send(embed=embed)
            print(f"[MENSAGEM] Embed enviado para #{welcome_channel.name}")
        except Exception as e:
            print(f"[ERRO] Ao enviar embed público: {e}")

        # Enviar DM com embed
        try:
            embed_dm = self.create_dm_embed(member, verify_channel, rules_channel)
            await member.send(embed=embed_dm)
            print(f"[DM] Embed enviado para {member.name}")
        except discord.Forbidden:
            print(f"[AVISO] {member.name} bloqueou DMs.")
        except Exception as e:
            print(f"[ERRO DM] {e}")

def setup(bot):
    bot.add_cog(Welcome(bot))