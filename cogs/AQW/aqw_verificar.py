import discord
from discord.ext import commands
from bs4 import BeautifulSoup
import aiohttp
import json
import random
import re
import unicodedata

# ID do cargo de verificação (substitua pelo real)
VERIFIED_ROLE_ID = 1234567890

# Tipos de itens a ignorar no inventário
IGNORED_TYPES = {"Item", "Resource", "Quest Item", "House", "Floor Item", "Wall Item"}


def normalize(text: str) -> str:
    """
    Normaliza o texto mantendo espaços e removendo apenas caracteres especiais.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ASCII", "ignore").decode("ASCII")
    cleaned = re.sub(r'[^a-zA-Z0-9 -]', '', ascii_text)  # Mantém espaços e hifens
    return cleaned.strip().lower()

def extract_equipped_items(soup: BeautifulSoup) -> tuple[list[str], BeautifulSoup | None]:
    """Extrai itens equipados da nova estrutura HTML."""
    equipped = []
    equipment_block = soup.find("div", class_="d-flex flex-rows flex-wrap justify-content-around")
    
    if equipment_block:
        # Encontra todas as divs que contêm os slots de equipamento
        slots = equipment_block.find_all("div", style="line-height: 85%")
        for slot in slots:
            # Extrai todos os links <a> dentro do slot (ignorando labels)
            item_links = slot.find_all("a")
            for item_link in item_links:
                raw_name = item_link.get_text(strip=True)
                if raw_name:  # Evita strings vazias
                    equipped.append(normalize(raw_name))
    
    return equipped, equipment_block
class VerificationView(discord.ui.View):
    def __init__(
        self,
        target_item: str,
        ccid: str,
        user_id: int,
        role_id: int
    ):
        super().__init__(timeout=300)
        self.target_item = target_item
        self.normalized_target = normalize(target_item)
        self.ccid = ccid
        self.user_id = user_id
        self.role_id = role_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirm(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        # Só quem iniciou pode confirmar
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ Você não iniciou esta verificação.",
                ephemeral=True
            )

        # Rebusca a página sem cache
        headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(f"https://account.aq.com/CharPage?id={self.ccid}") as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                equipped, equipment_block = extract_equipped_items(soup)

        # Verificação final
        if self.normalized_target in equipped:
            role = interaction.guild.get_role(self.role_id)
            await interaction.user.add_roles(role)
            await interaction.response.edit_message(
                content=f"✅ Verificação bem-sucedida! Item **{self.target_item}** equipado.",
                embed=None,
                view=None
            )
        else:
            itens = ', '.join(equipped) or 'Nenhum detectado'
            await interaction.response.send_message(
                f"❌ Falha na verificação\n"
                f"Esperado: `{self.target_item}`\n"
                f"Equipado: `{itens}`\n\n"
                "📌 Dicas:\n"
                "- Confira espaços e pontuação exata\n"
                "- Equipe em qualquer slot visível\n"
                "- Aguarde até 1 minuto após equipar",
                ephemeral=True
            )
        debug_msg = (
            f"**Debug:**\n"
            f"Target (Raw): {self.target_item}\n"
            f"Target (Norm): {self.normalized_target}\n"
            f"Equipped (Norm): {equipped}\n"
            f"HTML Block: {str(equipment_block)[:200]}..."  # Mostra parte do HTML analisado
        )
        

class VincularCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.users_file = "data/users.json"

    def load_users(self) -> dict:
        try:
            with open(self.users_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @discord.slash_command(
        name="verificar",
        description="Verifica sua conta AQW equipando um item aleatório"
    )
    async def verificar(
        self,
        ctx: discord.ApplicationContext,
        usuario: discord.Option(str, "Seu nickname")
    ):
        await ctx.defer(ephemeral=True)

        users = self.load_users()
        data = users.get(str(ctx.author.id))
        if not data:
            return await ctx.respond(
                "❌ Você não está vinculado a uma conta! Use /vincular primeiro.",
                ephemeral=True
            )

        ccid = data.get("ccid")
        async with aiohttp.ClientSession() as session:
            try:
                # Inventário
                inv_url = f"https://account.aq.com/CharPage/Inventory?ccid={ccid}"
                async with session.get(inv_url) as resp:
                    inventory = await resp.json()

                # Página do personagem
                char_url = f"https://account.aq.com/CharPage?id={ccid}"
                async with session.get(char_url) as resp:
                    soup = BeautifulSoup(await resp.text(), 'html.parser')

                equipped_items = extract_equipped_items(soup)

                # Itens elegíveis para verificação
                candidates = []
                for item in inventory:
                    name = item.get("strName", "")
                    t = normalize(name)
                    if (
                        t not in equipped_items
                        and item.get("strType") not in IGNORED_TYPES
                        and str(item.get("bUpgrade")).lower() != "true"
                    ):
                        candidates.append(name)

                if not candidates:
                    return await ctx.respond(
                        "❌ Nenhum item disponível para verificação. Tente novamente depois.",
                        ephemeral=True
                    )

                target = random.choice(candidates)
                embed = discord.Embed(
                    title="🔐 Verificação de Conta",
                    description=f"Equipe o seguinte item no seu personagem:\n\n**{target}**",
                    color=discord.Color.blue()
                )
                embed.set_footer(text="Você tem até 5 minutos para confirmar.")

                view = VerificationView(target, ccid, ctx.author.id, VERIFIED_ROLE_ID)
                msg = await ctx.respond(embed=embed, view=view)
                view.message = await msg.original_response()

            except Exception as e:
                await ctx.respond(f"❌ Erro ao processar verificação: {e}", ephemeral=True)


def setup(bot):
    bot.add_cog(VincularCog(bot))
