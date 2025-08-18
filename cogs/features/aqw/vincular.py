import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
import aiohttp
from bs4 import BeautifulSoup
import re
from database import db

class VincularCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.allowed_roles_ids = [1361379753503883516, 1361379753503883516, 1361222701259296778]  # IDs dos cargos permitidos

    async def get_ccid_from_nickname(self, nickname: str) -> int:
        """Obtém o CCID a partir do nickname do AQW."""
        url = f"https://account.aq.com/CharPage?id={nickname.replace(' ', '+')}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                scripts = soup.find_all('script')
                ccid_match = re.search(r"var ccid = (\d+)", scripts[6].string or "")
                return int(ccid_match.group(1)) if ccid_match else None

    def has_allowed_role(self, member: discord.Member) -> bool:
        """Verifica se o membro tem algum dos cargos permitidos."""
        return any(role.id in self.allowed_roles_ids for role in member.roles)

    vincular_group = SlashCommandGroup(
        "vincular", 
        "Sistema de vinculação de contas AQWorlds",
        guild_ids=[1361196873045643344]
    )

    @vincular_group.command(description="Vincula um membro usando CCID ou nickname do AQW")
    async def conta(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Membro do Discord"),
        identifier: Option(str, "CCID ou nickname do AQW"),
        force_ccid: Option(bool, "Forçar busca por CCID?", default=False)
    ):
        """Vincula uma conta AQW a um usuário do Discord."""
        await ctx.defer(ephemeral=True)

        # Verifica permissões
        if not self.has_allowed_role(ctx.author):
            return await ctx.respond("❌ Você não tem permissão para usar este comando!", ephemeral=True)
        
        # Verifica se o usuário existe no banco de dados
        if not db.check_user_exists(member.id):
            return await ctx.respond("❌ O usuário não está registrado no banco de dados!", ephemeral=True)

        # Obtém o CCID
        ccid = None
        if identifier.isdigit() and not force_ccid:
            ccid = int(identifier)
        else:
            ccid = await self.get_ccid_from_nickname(identifier)
            if not ccid:
                return await ctx.respond(f"❌ Nickname '{identifier}' não encontrado!", ephemeral=True)

        # Verifica se o CCID já está vinculado a outro usuário
        users = db.list_users()
        existing = next((u for u in users if u["aqw_id"] == ccid), None)
        if existing and existing["discord_id"] != member.id:
            return await ctx.respond(
                f"⚠️ CCID {ccid} já vinculado a <@{existing['discord_id']}>!",
                ephemeral=True
            )

        # Atualiza o usuário no banco de dados
        updates = {
            "aqw_id": ccid,
            "aqw_username": identifier if not identifier.isdigit() else None
        }
        
        if not db.update_user(member.id, **updates):
            return await ctx.respond("❌ Falha ao atualizar o usuário no banco de dados!", ephemeral=True)

        # Tenta atualizar nickname e cargo
        try:
            await member.edit(nick=identifier)
            role = ctx.guild.get_role(1361235200918556692)  # Substitua pelo ID do cargo desejado
            if role:
                await member.add_roles(role)
            
            await ctx.respond(
                f"✅ {member.mention} vinculado a CCID {ccid}\n"
                f"📛 Nickname e cargo atualizados!",
                ephemeral=True
            )
        except discord.Forbidden:
            await ctx.respond(
                "✅ Vinculação concluída, mas faltaram permissões para atualizar nickname/cargo",
                ephemeral=True
            )

def setup(bot):
    bot.add_cog(VincularCog(bot))