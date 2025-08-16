import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
import aiohttp
from bs4 import BeautifulSoup
import json
import os
import re

class VincularCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_path = "data/users.json"
        self.allowed_roles_ids = [1361379753503883516, 1361379753503883516, 1361222701259296778]  # 🛠 Substitua pelos IDs dos cargos permitidos

        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)

    async def get_ccid_from_nickname(self, nickname: str) -> int:
        url = f"https://account.aq.com/CharPage?id={nickname.replace(' ', '+')}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                scripts = soup.find_all('script')
                ccid_match = re.search(r"var ccid = (\d+)", scripts[6].string or "")
                return int(ccid_match.group(1)) if ccid_match else None

    def load_users(self):
        try:
            with open(self.data_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_users(self, users):
        with open(self.data_path, "w") as f:
            json.dump(users, f, indent=4)

    def has_allowed_role(self, member: discord.Member) -> bool:
        return any(role.id in self.allowed_roles_ids for role in member.roles)

    vincular_group = SlashCommandGroup(
        "vincular", 
        "Sistema de vinculação de contas AQWorlds",
        guild_ids=[1361196873045643344]
    )

    @vincular_group.command(description="Vincula um membro usando CCID ou nickname do AQW")
    async def conta(
        self,
        ctx,
        member: Option(discord.Member, "Membro do Discord"),
        identifier: Option(str, "CCID ou nickname do AQW"),
        force_ccid: Option(bool, "Forçar busca por CCID?", default=False)
    ):
        await ctx.defer(ephemeral=True)

        if not self.has_allowed_role(ctx.author):
            return await ctx.respond("❌ Você não tem permissão para usar este comando!", ephemeral=True)
        
        users = self.load_users()
        ccid = None

        if identifier.isdigit() and not force_ccid:
            ccid = int(identifier)
        else:
            ccid = await self.get_ccid_from_nickname(identifier)
            if not ccid:
                return await ctx.respond(f"❌ Nickname '{identifier}' não encontrado!", ephemeral=True)

        existing = next((u for u in users.values() if u["ccid"] == ccid), None)
        if existing:
            return await ctx.respond(
                f"⚠️ CCID {ccid} já vinculado a <@{existing['discord_id']}>!",
                ephemeral=True
            )

        user_data = {
            "discord_id": member.id,
            "ccid": ccid,
            "nickname": identifier if not identifier.isdigit() else None,
            "matchmaking": {"available": False, "queue": None}
        }

        users[str(member.id)] = user_data
        self.save_users(users)

        try:
            await member.edit(nick=identifier)
            role = ctx.guild.get_role(1361235200918556692)
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
