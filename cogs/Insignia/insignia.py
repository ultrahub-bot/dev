import discord
from discord.ext import commands
from discord import Option
import json
import os
import requests
import config

class InsigniaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.insignias_file = config.INSIGNIAS_FILE  # Usando config
        self.load_insignias()

    def load_insignias(self):
        """Carrega os dados das insígnias do arquivo JSON"""
        os.makedirs(os.path.dirname(self.insignias_file), exist_ok=True)
        try:
            with open(self.insignias_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_insignias(self, data):
        """Salva os dados atualizados no arquivo JSON"""
        with open(self.insignias_file, "w") as f:
            json.dump(data, f, indent=4)

    @discord.slash_command(name="insignia", description="Verifica requisitos para um cargo")
    async def insignia(self, ctx, role: Option(discord.Role, "Cargo para verificar")):
        await ctx.defer()
        
        # Verifica vinculação do usuário
        try:
            with open(config.USERS_FILE, "r") as f:  # Usando config
                users = json.load(f)
        except FileNotFoundError:
            return await ctx.respond("❌ Arquivo de usuários não encontrado!", ephemeral=True)
        
        if str(ctx.author.id) not in users:
            return await ctx.respond("❌ Você não está vinculado a uma conta!", ephemeral=True)

        # Carrega requisitos
        insignias = self.load_insignias()
        requirements = insignias.get(str(role.id))

        if not requirements:
            return await ctx.respond("⚠️ Este cargo não possui requisitos configurados!", ephemeral=True)

        # Verificação de progresso
        ccid = users[str(ctx.author.id)]["ccid"]
        inventory = requests.get(f"https://account.aq.com/CharPage/Inventory?ccid={ccid}").json()
        badges = requests.get(f"https://account.aq.com/CharPage/Badges?ccid={ccid}").json()
        
        missing = []
        
        # Verificação de itens
        if "items" in requirements:
            for item in requirements["items"]:
                found = [i for i in inventory if item["name"].lower() in i["strName"].lower()]
                total = sum(i["intCount"] for i in found)
                
                if item.get("min", 0) > total:
                    missing.append(
                        f"❌ {item['name']} " +
                        f"(Possui: {total}/Requer: {item['min']})" if item.get("min") else ""
                    )

        # Verificação de badges
        if "badges" in requirements:
            for badge_id in requirements["badges"]:
                if not any(b["badgeID"] == badge_id for b in badges):
                    missing.append(f"🎖️ Badge ID {badge_id} não encontrada")

        # Verificação de cargos
        if "required_roles" in requirements:
            for role_id in requirements["required_roles"]:
                required_role = ctx.guild.get_role(role_id)
                if required_role and required_role not in ctx.author.roles:
                    missing.append(f"📛 {required_role.name}")

        if not missing:
            await ctx.author.add_roles(role)
            await ctx.respond(f"✅ Você recebeu o cargo **{role.name}**!", ephemeral=True)
        else:
            await ctx.respond(
                f"❌ Faltam {len(missing)} requisitos para **{role.name}**:\n" + 
                "\n".join(missing),
                ephemeral=True
            )

    @discord.slash_command(name="criar_insignia", description="Configura requisitos para um cargo (Admin)")
    @commands.has_permissions(administrator=True)
    async def criar_insignia(
        self,
        ctx,
        role: Option(discord.Role, "Cargo alvo"),
        items: Option(str, "Formato: nome:quantidade separados por vírgula", required=False),
        badges: Option(str, "IDs separados por vírgula", required=False),
        roles: Option(str, "IDs de cargos separados por vírgula", required=False)
    ):
        insignias = self.load_insignias()
        new_requirements = {}

        # Processamento de itens
        if items:
            new_requirements["items"] = []
            for item in items.split(","):
                parts = item.split(":")
                item_data = {"name": parts[0].strip()}
                if len(parts) > 1:
                    item_data["min"] = int(parts[1])
                new_requirements["items"].append(item_data)

        # Processamento de badges
        if badges:
            new_requirements["badges"] = [int(b.strip()) for b in badges.split(",")]

        # Processamento de cargos
        if roles:
            new_requirements["required_roles"] = [int(r.strip()) for r in roles.split(",")]

        insignias[str(role.id)] = new_requirements
        self.save_insignias(insignias)
        
        await ctx.respond(
            f"✅ Requisitos para **{role.name}** atualizados:\n" +
            json.dumps(new_requirements, indent=2),
            ephemeral=True
        )

    @discord.slash_command(name="remover_insignia", description="Remove requisitos de um cargo (Admin)")
    @commands.has_permissions(administrator=True)
    async def remover_insignia(self, ctx, role: Option(discord.Role, "Cargo alvo")):
        insignias = self.load_insignias()
        
        if str(role.id) in insignias:
            del insignias[str(role.id)]
            self.save_insignias(insignias)
            await ctx.respond(f"❌ Requisitos de **{role.name}** removidos.", ephemeral=True)
        else:
            await ctx.respond("ℹ️ Este cargo não possui requisitos cadastrados.", ephemeral=True)

def setup(bot):
    bot.add_cog(InsigniaCog(bot))