import json
import discord
from discord.ext import commands
from discord.commands import Option, SlashCommandGroup
from pathlib import Path
from typing import List, Dict

class CompSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_dir = Path("./data")
        self.comps_dir = self.data_dir / "comps"
        self.comps_dir.mkdir(parents=True, exist_ok=True)
        self.admin_roles = {0000000000000000}  # IDs de cargos admin

    comp = SlashCommandGroup("comp", "Gerenciar composições de raid")

    async def is_admin(self, user: discord.Member) -> bool:
        return any(role.id in self.admin_roles for role in user.roles)

    def _validate_comp(self, data: dict) -> None:
        required = {
            "name": str,
            "classes": list,
            "strategy": str,
            "author": str
        }
        for field, ftype in required.items():
            if not isinstance(data.get(field), ftype):
                raise ValueError(f"Campo '{field}' deve ser {ftype.__name__}")
        if len(data["classes"]) < 1:
            raise ValueError("Pelo menos 1 classe deve ser especificada")

    def _get_comps_file(self, boss: str) -> Path:
        return self.comps_dir / f"{boss}.json"

    def _load_comps(self, boss: str) -> List[Dict]:
        comp_file = self._get_comps_file(boss)
        if not comp_file.exists():
            return []
        with open(comp_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_comps(self, boss: str, comps: List[Dict]) -> None:
        with open(self._get_comps_file(boss), "w", encoding="utf-8") as f:
            json.dump(comps, f, indent=4, ensure_ascii=False)

    @comp.command(name="criar", description="Adiciona nova composição")
    async def criar_comp(
        self,
        ctx: discord.ApplicationContext,
        boss: Option(str, "Nome do Ultra Boss", autocomplete=lambda i, c: [
            boss for boss in ["Ultra Warden", "Ultra Engineer", "Champion Drakath"]
        ]),
        comp_json: Option(str, "JSON da composição", min_length=30)
    ):
        await ctx.defer(ephemeral=True)
        
        if not await self.is_admin(ctx.author):
            return await ctx.respond("❌ Apenas administradores podem criar composições!", ephemeral=True)

        try:
            comp_data = json.loads(comp_json.replace('`', ''))
            self._validate_comp(comp_data)
            
            comps = self._load_comps(boss)
            if any(c["name"].lower() == comp_data["name"].lower() for c in comps):
                return await ctx.respond("❌ Já existe uma composição com esse nome!", ephemeral=True)

            comps.append(comp_data)
            self._save_comps(boss, comps)
            
            embed = discord.Embed(
                title=f"✅ Nova composição para {boss}",
                description=f"**{comp_data['name']}** criada com sucesso!",
                color=discord.Color.green()
            )
            await ctx.respond(embed=embed, ephemeral=True)

        except Exception as e:
            await ctx.respond(f"❌ Erro: {str(e)}", ephemeral=True)

    @comp.command(name="listar", description="Lista composições de um boss")
    async def listar_comps(
        self,
        ctx: discord.ApplicationContext,
        boss: Option(str, "Nome do Ultra Boss", autocomplete=lambda i, c: [
            boss for boss in ["Ultra Warden", "Ultra Engineer", "Champion Drakath"]
        ])
    ):
        await ctx.defer(ephemeral=True)
        
        comps = self._load_comps(boss)
        if not comps:
            return await ctx.respond(f"❌ Nenhuma composição encontrada para {boss}!", ephemeral=True)

        embed = discord.Embed(
            title=f"📋 Composições de {boss}",
            color=discord.Color.blue()
        )
        
        for comp in comps:
            classes = "\n".join(f"• {cls}" for cls in comp["classes"])
            embed.add_field(
                name=f"🔹 {comp['name']} (por {comp['author']})",
                value=f"**Classes:**\n{classes}\n\n**Estratégia:**\n{comp['strategy'][:200]}...",
                inline=False
            )
        
        await ctx.respond(embed=embed, ephemeral=True)

    @comp.command(name="remover", description="Remove uma composição")
    async def remover_comp(
        self,
        ctx: discord.ApplicationContext,
        boss: Option(str, "Nome do Ultra Boss"),
        nome_comp: Option(str, "Nome da composição")
    ):
        await ctx.defer(ephemeral=True)
        
        if not await self.is_admin(ctx.author):
            return await ctx.respond("❌ Apenas administradores podem remover composições!", ephemeral=True)

        comps = self._load_comps(boss)
        original_count = len(comps)
        comps = [c for c in comps if c["name"].lower() != nome_comp.lower()]
        
        if len(comps) == original_count:
            return await ctx.respond("❌ Composição não encontrada!", ephemeral=True)

        self._save_comps(boss, comps)
        await ctx.respond(f"✅ Composição **{nome_comp}** removida de {boss}!", ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(CompSystem(bot))