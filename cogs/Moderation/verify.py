import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import json
import os
import config

class VerifyButton(Button):
    def __init__(self, pending_role_id: int, verified_role_id: int):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Verify / Verificar",
            emoji="✅",
            custom_id="verify_button"
        )
        self.pending_role_id = pending_role_id
        self.verified_role_id = verified_role_id

    async def callback(self, interaction: discord.Interaction):
        pending_role = interaction.guild.get_role(self.pending_role_id)
        verified_role = interaction.guild.get_role(self.verified_role_id)

        try:
            if pending_role and pending_role in interaction.user.roles:
                await interaction.user.remove_roles(pending_role)
            if verified_role and verified_role not in interaction.user.roles:
                await interaction.user.add_roles(verified_role)

            await interaction.response.send_message(
                "✅ Verification complete! Welcome to the server!\n"
                "✅ Verificação concluída! Bem-vindo ao servidor!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Bot lacks permissions to manage roles!\n"
                "❌ Bot não tem permissão para gerenciar cargos!",
                ephemeral=True
            )

class VerificationView(View):
    def __init__(self, pending_role_id: int, verified_role_id: int):
        super().__init__(timeout=None)
        self.add_item(VerifyButton(pending_role_id, verified_role_id))

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.storage_file = config.VERIFY_STORAGE  # Usando config
        self.verification_data = {}
        self.bot.loop.create_task(self.rebuild_verification_view())

    @commands.Cog.listener()
    async def on_ready(self):
        print("[Verification] Cog carregado com sucesso.")

    @discord.slash_command(
        name="setup", 
        description="Configura o sistema de verificação", 
        guild_ids=[config.BOT_SERVER]  # Usando config
    )
    @commands.has_permissions(administrator=True)
    async def setup(
        self,
        ctx: discord.ApplicationContext,
        channel: discord.Option(discord.TextChannel, "Canal"),
        pending_role: discord.Option(discord.Role, "Cargo pendente"),
        verified_role: discord.Option(discord.Role, "Cargo verificado")
    ):
        embed = discord.Embed(color=0x2b2d31)
        embed.title = "🔒 Verification System / Sistema de Verificação"
        embed.description = (
            "**English:**\nClick below to verify yourself.\n\n"
            "**Português:**\nClique abaixo para se verificar."
        )
        embed.set_footer(text="Security System", icon_url=self.bot.user.display_avatar.url)
        embed.add_field(name="Rules", value=f"{pending_role.mention} → {verified_role.mention}", inline=False)

        view = VerificationView(pending_role.id, verified_role.id)
        message = await channel.send(embed=embed, view=view)
        await ctx.respond(f"✅ Sistema configurado em {channel.mention}", ephemeral=True)

        # Salva a mensagem
        self.verification_data = {
            "channel_id": channel.id,
            "message_id": message.id,
            "pending_role": pending_role.id,
            "verified_role": verified_role.id
        }
        self.save_data()

    def save_data(self):
        os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
        with open(self.storage_file, "w") as f:
            json.dump(self.verification_data, f)

    async def rebuild_verification_view(self):
        await self.bot.wait_until_ready()
        if not os.path.exists(self.storage_file):
            return
        with open(self.storage_file, "r") as f:
            self.verification_data = json.load(f)

        try:
            channel = self.bot.get_channel(self.verification_data["channel_id"])
            if not channel:
                return

            message = await channel.fetch_message(self.verification_data["message_id"])
            view = VerificationView(
                self.verification_data["pending_role"],
                self.verification_data["verified_role"]
            )
            await message.edit(view=view)
        except Exception as e:
            print(f"[Verification] Falha ao reconstruir view da verificação: {e}")

def setup(bot):
    bot.add_cog(Verification(bot))