import discord
from discord.ext import commands
from bs4 import BeautifulSoup
import aiohttp
import re

class AQChar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch_html(self, session, url):
        async with session.get(url) as resp:
            return BeautifulSoup(await resp.text(), 'html.parser')

    async def fetch_json(self, session, url):
        async with session.get(url) as resp:
            return await resp.json()

    def extract_ccid(self, scripts):
        script_texts = [s.string for s in scripts if s and s.string]
        for script in script_texts:
            match = re.search(r"var ccid = (\d+)", script)
            if match:
                return match.group(1)
        return "????"

    def parse_status_warning(self, bodyinfo):
        status_map = {
            "Disabled": ("Disabled", "Cheating, Rules Violations, or Payment Fraud."),
            "wandering": ("AFK", "Account has __not logged in__ for years."),
            "Locked": ("Locked", "Unknown. Contact support for help."),
        }

        for key, (status, reason) in status_map.items():
            if key in bodyinfo:
                return f"**Status**: {status}\n**Reason**: {reason}"
        return f"**Status**: {bodyinfo}"

    def build_char_info(self, details):
        char_infos = {}
        excluded = ["Level", "Faction", "Guild"]
        for line in details.text.strip().split("\n"):
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
        return char_infos

    def build_inventory_summary(self, inv_data):
        ioda_count = 0
        tp_count = 0
        ioda_items = ""

        for item in inv_data:
            name = item["strName"]
            if "of Digital Awesomeness" in name:
                ioda_count += 1
            if "Treasure Potion" in name:
                tp_count = int(item.get("intCount", 0))
            if "IoDA" in name:
                ioda_items += f"• {name.strip()}\n"

        return ioda_count, tp_count, ioda_items

    @discord.slash_command(name="char", description="Consulta o perfil de um personagem do AQWorlds")
    async def char(self, ctx: discord.ApplicationContext, character_name: discord.Option(str, "Nome do personagem")):
        await ctx.defer()
        args = character_name.strip()
        player_url = f"https://account.aq.com/CharPage?id={args.replace(' ', '+')}"

        async with aiohttp.ClientSession() as session:
            soup = await self.fetch_html(session, player_url)

            name_tag = soup.select_one(".card-header h1")
            player_name = name_tag.text.strip() if name_tag else args
            safe_name = player_name.replace("__", "\\_")

            details = soup.select_one(".card-body .row")
            if not details or not details.text.strip():
                bodyinfo = soup.select_one('.card-body').text.strip() if soup.select_one('.card-body') else ""
                if not bodyinfo:
                    embed = discord.Embed(
                        title=safe_name,
                        url=player_url,
                        description="Character not found.",
                        color=discord.Color.red()
                    )
                    embed.set_author(name="Character Profile")
                    embed.set_thumbnail(url="https://cdn.aq.com/resources/images/not_found.png")
                    return await ctx.respond(embed=embed)

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

            char_infos = self.build_char_info(details)

            scripts = soup.find_all('script')
            ccid = self.extract_ccid(scripts)
            inventory_url = f"https://account.aq.com/CharPage/Inventory?ccid={ccid}"
            inv_data = await self.fetch_json(session, inventory_url)

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
                inv_field += f"\nIoDA Token: {ioda_count}\n"
            if ioda_items:
                inv_field += f"IoDA Items:\n{ioda_items}\n"

            embed.add_field(name="Inventory:", value=f"```YAML\n{inv_field}```", inline=False)

        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(AQChar(bot))
