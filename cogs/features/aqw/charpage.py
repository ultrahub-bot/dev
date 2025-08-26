import discord
from discord.ext import commands
from bs4 import BeautifulSoup
import aiohttp
import re
import logging

# Configuração de logging melhorada
logger = logging.getLogger(__name__)

class AQChar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Cog AQChar carregada")

    async def fetch_html(self, session, url):
        try:
            logger.info(f"Buscando HTML: {url}")
            async with session.get(url, timeout=10) as resp:
                logger.info(f"Status HTTP: {resp.status} para {url}")
                if resp.status == 200:
                    html = await resp.text()
                    logger.info(f"HTML recebido ({len(html)} caracteres)")
                    return BeautifulSoup(html, 'html.parser')
                else:
                    logger.warning(f"HTTP {resp.status} ao acessar {url}")
                    return None
        except Exception as e:
            logger.error(f"Erro ao buscar HTML: {e}")
            return None

    async def fetch_json(self, session, url):
        try:
            logger.info(f"Buscando JSON: {url}")
            async with session.get(url, timeout=10) as resp:
                logger.info(f"Status HTTP JSON: {resp.status} para {url}")
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"JSON recebido: {len(data)} itens")
                    return data
                else:
                    logger.warning(f"HTTP {resp.status} ao acessar JSON: {url}")
                    return []
        except Exception as e:
            logger.error(f"Erro ao buscar JSON: {e}")
            return []

    def extract_ccid(self, scripts):
        logger.info("Extraindo CCID dos scripts")
        script_texts = [s.string for s in scripts if s and s.string]
        for i, script in enumerate(script_texts):
            if script:
                match = re.search(r"var ccid = (\d+)", script)
                if match:
                    ccid = match.group(1)
                    logger.info(f"CCID encontrado: {ccid}")
                    return ccid
        logger.warning("CCID não encontrado nos scripts")
        return "????"

    def parse_status_warning(self, bodyinfo):
        logger.info(f"Analisando status: {bodyinfo[:100]}...")
        status_map = {
            "Disabled": ("Disabled", "Cheating, Rules Violations, or Payment Fraud."),
            "wandering": ("AFK", "Account has __not logged in__ for years."),
            "Locked": ("Locked", "Unknown. Contact support for help."),
        }

        for key, (status, reason) in status_map.items():
            if key in bodyinfo:
                logger.info(f"Status especial detectado: {status}")
                return f"**Status**: {status}\n**Reason**: {reason}"
        logger.info(f"Status genérico: {bodyinfo}")
        return f"**Status**: {bodyinfo}"

    def build_char_info(self, details):
        logger.info("Construindo informações do personagem")
        char_infos = {}
        excluded = ["Level", "Faction", "Guild"]
        lines = details.text.strip().split("\n")
        logger.info(f"{len(lines)} linhas encontradas para processar")
        
        for line in lines:
            if ":" not in line:
                continue
            key, value = map(str.strip, line.split(":", 1))
            if not value:
                continue
            if key in excluded:
                char_infos[key] = value
            else:
                wiki_link = f"https://aqwwiki.wikidot.com/search:site/q/{value.replace(' ', '+')}/type/thread"
                char_infos[key] = f"[{value}]({wiki_link})"
        
        logger.info(f"Informações do personagem: {list(char_infos.keys())}")
        return char_infos

    def build_inventory_summary(self, inv_data):
        logger.info("Analisando inventário")
        ioda_count = 0
        tp_count = 0
        ioda_items = ""

        if not inv_data or not isinstance(inv_data, list):
            logger.warning("Dados de inventário inválidos ou vazios")
            return ioda_count, tp_count, ioda_items

        logger.info(f"Processando {len(inv_data)} itens do inventário")
        
        for item in inv_data:
            name = item.get("strName", "")
            count = int(item.get("intCount", 1))

            # Contagem de IoDA tokens
            if "of Digital Awesomeness" in name:
                ioda_count += count
                logger.debug(f"IoDA token encontrado: {name} x{count}")

            # Treasure Potions
            if "Treasure Potion" in name:
                tp_count = count
                logger.debug(f"Treasure Potion encontrada: {name} x{count}")

            # Itens IoDA (recompensas)
            if any(tag in name for tag in ["IoDA", "(IoDA)", "of Digital Awesomeness"]):
                ioda_items += f"• {name.strip()}\n"
                logger.debug(f"Item IoDA encontrado: {name}")

        logger.info(f"Resumo inventário: {ioda_count} IoDA tokens, {tp_count} Treasure Potions, {len(ioda_items.splitlines())} itens IoDA")
        return ioda_count, tp_count, ioda_items

    @discord.slash_command(name="char", description="Consulta o perfil de um personagem do AQWorlds")
    async def char(self, ctx: discord.ApplicationContext, character_name: discord.Option(str, "Nome do personagem")):
        try:
            await ctx.defer()
            args = character_name.strip()
            player_url = f"https://account.aq.com/CharPage?id={args.replace(' ', '+')}"
            
            logger.info(f"═══════════════════════════════════════════════════")
            logger.info(f"Comando /char executado para: '{args}'")
            logger.info(f"URL: {player_url}")

            async with aiohttp.ClientSession() as session:
                logger.info("Buscando página HTML do personagem...")
                soup = await self.fetch_html(session, player_url)
                
                if soup is None:
                    logger.error("Falha ao obter HTML do personagem")
                    embed = discord.Embed(
                        title=args,
                        url=player_url,
                        description="Erro ao acessar a página do personagem.",
                        color=discord.Color.red()
                    )
                    embed.set_author(name="Character Profile")
                    embed.set_thumbnail(url="https://cdn.aq.com/resources/images/not_found.png")
                    return await ctx.respond(embed=embed)

                # Verifica se encontrou o nome do personagem
                name_tag = soup.select_one(".card-header h1")
                if name_tag:
                    player_name = name_tag.text.strip()
                    logger.info(f"Nome do personagem encontrado: {player_name}")
                else:
                    player_name = args
                    logger.warning("Nome do personagem não encontrado no HTML")

                safe_name = player_name.replace("__", "\\_")

                # Verifica se encontrou os detalhes
                details = soup.select_one(".card-body .row")
                if not details or not details.text.strip():
                    logger.warning("Detalhes do personagem não encontrados")
                    bodyinfo = soup.select_one('.card-body').text.strip() if soup.select_one('.card-body') else ""
                    
                    if not bodyinfo:
                        logger.info("Personagem não encontrado")
                        embed = discord.Embed(
                            title=safe_name,
                            url=player_url,
                            description="Character not found.",
                            color=discord.Color.red()
                        )
                        embed.set_author(name="Character Profile")
                        embed.set_thumbnail(url="https://cdn.aq.com/resources/images/not_found.png")
                        return await ctx.respond(embed=embed)

                    logger.info("Personagem encontrado mas com status especial")
                    warn = self.parse_status_warning(bodyinfo)
                    embed = discord.Embed(
                        title=safe_name,
                        url=player_url,
                        description=warn,
                        color=discord.Color.orange()
                    )
                    embed.set_author(name="Character Profile")
                    embed.set_thumbnail(url="https://cdn.aq.com/resources/images/lock.png")
                    return await ctx.respond(embed=embed)

                logger.info("Personagem encontrado - processando informações...")
                char_infos = self.build_char_info(details)

                # Extrai CCID
                scripts = soup.find_all('script')
                logger.info(f"Encontrados {len(scripts)} scripts na página")
                ccid = self.extract_ccid(scripts)
                
                # CORREÇÃO AQUI: URL correta do inventário
                inventory_url = f"https://account.aq.com/CharPage/Inventory?ccid={ccid}"
                logger.info(f"Buscando inventário: {inventory_url}")
                
                inv_data = await self.fetch_json(session, inventory_url)
                logger.info(f"Inventário processado: {len(inv_data)} itens")

            # Organiza o Embed
            embed = discord.Embed(
                title=safe_name,
                url=player_url,
                color=discord.Color.dark_green(),
            )
            embed.set_author(name="Character Profile")
            embed.set_thumbnail(url="https://cdn.aq.com/resources/images/aqw_icon_long.png")

            # Descrição e equipamentos
            desc = ""
            equips = ""
            principais = ["Name", "Level", "Class", "Faction", "Guild"]

            for key, val in char_infos.items():
                if key in principais:
                    desc += f"{key}: {val}\n"
                else:
                    equips += f"{key}: {val}\n"
            desc += f"ID: [{ccid}]({inventory_url})"
            embed.description = desc

            if equips:
                embed.add_field(name="Equipment:", value=equips, inline=False)

            # Itens do inventário
            ioda_count, tp_count, ioda_items = self.build_inventory_summary(inv_data)
            if tp_count or ioda_count or ioda_items:
                inv_field = ""
                if tp_count:
                    inv_field += f"Treasure Potion: {tp_count}\n"
                if ioda_count:
                    inv_field += f"IoDA Token: {ioda_count}\n"
                if ioda_items:
                    inv_field += f"IoDA Items:\n{ioda_items}\n"

                embed.add_field(name="Inventory:", value=f"```YAML\n{inv_field}```", inline=False)
            else:
                logger.info("Nenhum item relevante encontrado no inventário")

            logger.info("Embed construído com sucesso - enviando resposta...")
            await ctx.respond(embed=embed)
            logger.info(f"Comando /char concluído para: '{args}'")
            logger.info("═══════════════════════════════════════════════════")

        except Exception as e:
            logger.error(f"Erro inesperado no comando /char: {e}")
            embed = discord.Embed(
                title="Erro",
                description="Ocorreu um erro interno ao processar o comando.",
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(AQChar(bot))