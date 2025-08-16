# cogs/raid_free.py
import discord
from discord.ext import commands
from discord.commands import Option
from discord.ui import View, Button
import json, time, random
from pathlib import Path

class RaidSystem(commands.Cog):
    THREAD_PREFIX = "⚔️ [Raid] "

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_raids = {}
        self.raid_channel_id = 1361368164193145055  # <-- troque para o canal certo
        self.data_dir = Path("data")
        self.boss_file = self.data_dir / "ultra-bosses.json"

        if not self.boss_file.exists():
            raise FileNotFoundError("Arquivo ultra-bosses.json não encontrado!")

        with open(self.boss_file, "r", encoding="utf-8") as f:
            self.bosses_data = json.load(f)

        # Filtrar apenas os bosses visíveis
        self.visible_bosses = [
            name for name, data in self.bosses_data.items()
            if not str(data.get("hide", "false")).lower() == "true"
        ]

    raid = discord.SlashCommandGroup("raid", "Sistema simples de raid (modo livre)")

    async def get_visible_bosses(self, ctx: discord.AutocompleteContext):
        return [b for b in self.visible_bosses if ctx.value.lower() in b.lower()]

    @raid.command(name="criar", description="Cria uma nova raid contra um Ultra Boss (modo livre)")
    async def criar_raid(
        self,
        ctx: discord.ApplicationContext,
        boss: Option(str, "Escolha o boss", autocomplete=get_visible_bosses)
    ):
        await ctx.defer(ephemeral=True)

        raid_id = f"{ctx.author.id}-{int(time.time())}"
        party_size = self.bosses_data[boss]["party_size"]

        raid_data = {
            "boss": boss,
            "creator": ctx.author.id,
            "status": "recruiting",
            "party_size": party_size,
            "members": {str(ctx.author.id): True},
            "created_at": time.time()
        }
        self.active_raids[raid_id] = raid_data

        channel = self.bot.get_channel(self.raid_channel_id)
        if not channel:
            return await ctx.respond("❌ Canal de raids não encontrado!", ephemeral=True)

        # Mensagem principal
        embed = self.create_raid_embed(raid_data)
        main_msg = await channel.send(
            content=f"🔥 Nova raid contra **{boss}** criada por <@{ctx.author.id}>!",
            embed=embed
        )

        # Thread
        thread = await main_msg.create_thread(
            name=f"{self.THREAD_PREFIX}{boss}",
            auto_archive_duration=1440
        )
        raid_data["thread_id"] = thread.id
        raid_data["message_id"] = main_msg.id

        # Painel inicial
        control_embed = discord.Embed(
            title=f"⚔️ Raid contra {boss}",
            description=f"Modo LIVRE - Slots {len(raid_data['members'])}/{raid_data['party_size']}",
            color=discord.Color.gold()
        )
        participants = "\n".join([f"<@{uid}>" for uid in raid_data['members']])
        control_embed.add_field(name="Participantes", value=participants, inline=False)

        control_msg = await thread.send(embed=control_embed, view=ThreadRaidView(self, raid_id))
        await control_msg.pin()

        # Botão de link na mensagem principal
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="Ir para a Thread",
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{channel.guild.id}/{thread.id}"
        ))
        await main_msg.edit(view=view)

        await ctx.respond(f"✅ Raid criada em {thread.mention}!", ephemeral=True)

    def create_raid_embed(self, raid):
        boss_data = self.bosses_data[raid["boss"]]
        embed = discord.Embed(
            title=f"Raid: {raid['boss']}",
            description=f"👑 Criador: <@{raid['creator']}>\n"
                        f"👥 {len(raid['members'])}/{raid['party_size']} jogadores\n"
                        f"🗺️ Mapa: `{boss_data['map']}`\n"
                        f"⚡ Dificuldade: `{boss_data['difficulty']}`",
            color=discord.Color.blue()
        )
        if boss_data.get("thumbnail_url"):
            embed.set_thumbnail(url=boss_data["thumbnail_url"])
        return embed

    async def update_thread_panel(self, raid_id: str):
        raid = self.active_raids.get(raid_id)
        if not raid:
            return
        thread = self.bot.get_channel(raid["thread_id"])
        if not thread:
            return

        pinned = await thread.pins()
        control_msg = next((m for m in pinned if m.embeds), None)
        if not control_msg:
            return

        embed = discord.Embed(
            title=f"⚔️ Raid contra {raid['boss']}",
            description=f"Modo LIVRE - Slots {len(raid['members'])}/{raid['party_size']}",
            color=discord.Color.gold()
        )
        participants = "\n".join([f"<@{uid}>" for uid in raid["members"]]) or "Nenhum ainda"
        embed.add_field(name="Participantes", value=participants, inline=False)

        await control_msg.edit(embed=embed, view=ThreadRaidView(self, raid_id))


class ThreadRaidView(View):
    def __init__(self, cog: RaidSystem, raid_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.raid_id = raid_id
        self.add_item(JoinRaidButton(cog, raid_id))
        self.add_item(LeaveRaidButton(cog, raid_id))


class JoinRaidButton(Button):
    def __init__(self, cog: RaidSystem, raid_id: str):
        super().__init__(label="Entrar", style=discord.ButtonStyle.green, emoji="🛡️")
        self.cog = cog
        self.raid_id = raid_id

    async def callback(self, interaction: discord.Interaction):
        raid = self.cog.active_raids.get(self.raid_id)
        if not raid:
            return await interaction.response.send_message("❌ Raid não encontrada!", ephemeral=True)
        if str(interaction.user.id) in raid["members"]:
            return await interaction.response.send_message("❌ Você já está na raid!", ephemeral=True)
        if len(raid["members"]) >= raid["party_size"]:
            return await interaction.response.send_message("❌ Raid cheia!", ephemeral=True)

        raid["members"][str(interaction.user.id)] = True
        await self.cog.update_thread_panel(self.raid_id)
        await interaction.response.send_message("✅ Você entrou na raid!", ephemeral=True)


class LeaveRaidButton(Button):
    def __init__(self, cog: RaidSystem, raid_id: str):
        super().__init__(label="Sair", style=discord.ButtonStyle.red)
        self.cog = cog
        self.raid_id = raid_id

    async def callback(self, interaction: discord.Interaction):
        raid = self.cog.active_raids.get(self.raid_id)
        if not raid or str(interaction.user.id) not in raid["members"]:
            return await interaction.response.send_message("❌ Você não está na raid!", ephemeral=True)
        del raid["members"][str(interaction.user.id)]
        await self.cog.update_thread_panel(self.raid_id)
        await interaction.response.send_message("✅ Você saiu da raid!", ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(RaidSystem(bot))
    print("RaidSystem cog loaded successfully.")