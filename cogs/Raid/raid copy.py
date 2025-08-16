import discord
from discord.ext import commands
from discord.commands import Option, SlashCommandGroup
from discord.ui import Button, View, Select
from discord import ButtonStyle
import json
import asyncio
import time
import requests
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, TypedDict, Literal


class BossData(TypedDict):
    difficulty: str
    map: str
    party_size: int
    comps: List[Dict[str, str]]

class RaidData(TypedDict):
    boss: str
    comp: str
    creator: int
    status: Literal["recruiting", "confirming","in progress","completed", "canceled"]
    party_size: int
    members: Dict[str, str]
    available_classes: List[str]
    message_id: Optional[int]
    strategy: str
    created_at: float

class RaidSystem(commands.Cog):
    THREAD_PREFIX = "⚔️ [Raid] "

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_raids: Dict[str, RaidData] = {}
        self.raid_channel_id = 1361368164193145055
        self.data_dir = Path("./data")
        self.raids_dir = self.data_dir / "raids"
        self.logs_dir = self.data_dir / "raid_logs"
        self._setup_directories()
        self.comps_dir = self.data_dir / "comps"
        self.pending_selections: Set[int] = set()  
        # Ordem corrigida
        self.load_boss_data()  # Deve vir primeiro
        self.load_raids()
        self.load_comps()
        
        self.cleanup_task = self.bot.loop.create_task(self.cleanup_inactive_raids())
        self.rebuild_task = self.bot.loop.create_task(self.rebuild_all_raid_views())

    def load_comps(self):
        self.comps_data = {}
        for comp_file in self.comps_dir.glob("*.json"):
            try:
                with open(comp_file, "r", encoding="utf-8") as f:
                    self.comps_data[comp_file.stem] = json.load(f)
            except Exception as e:
                print(f"Erro ao carregar composições para {comp_file.stem}: {str(e)}")

    def get_comps_for_boss(self, boss: str) -> list:
        return self.comps_data.get(boss, [])

    def _setup_directories(self) -> None:
        self.raids_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _get_dynamic_available_classes(self, raid: RaidData) -> List[str]:
        boss_comps = self.comps_data.get(raid["boss"], [])
        
        # Ignorar valores como "PENDING"
        selected_classes = {cls for cls in raid["members"].values() if cls != "PENDING"}
        
        valid_classes = set()

        if raid["comp"].lower() == "meta":
            for comp in boss_comps:
                comp_classes = set(comp["classes"])
                if selected_classes.issubset(comp_classes):
                    valid_classes.update(comp_classes - selected_classes)
        else:
            comp = next((c for c in boss_comps if c["name"].lower() == raid["comp"].lower()), None)
            if comp:
                comp_classes = set(comp["classes"])
                if selected_classes.issubset(comp_classes):
                    valid_classes.update(comp_classes - selected_classes)

        return sorted(valid_classes)

    def load_boss_data(self) -> None:
        boss_file = self.data_dir / "ultra-bosses.json"
        if not boss_file.exists():
            raise FileNotFoundError(f"Arquivo de bosses não encontrado: {boss_file}")
        
        with open(boss_file, "r", encoding="utf-8") as f:
            self.bosses_data: Dict[str, BossData] = json.load(f)
        
        # Nova lógica para bosses visíveis (mantendo dados originais intactos)
        self.visible_bosses = [
            boss_name for boss_name, data in self.bosses_data.items()
            if not str(data.get("hide", "false")).lower() == "true"
        ]

    def load_raids(self) -> None:
        for file in self.raids_dir.glob("*.json"):
            with open(file, "r", encoding="utf-8") as f:
                raid: RaidData = json.load(f)
                self.active_raids[file.stem] = raid
                # Apenas marca as raids que precisam ser reconstruídas
                raid["needs_rebuild"] = raid["status"] in ["recruiting", "confirming"]

    async def autocomplete_classes(self, ctx: discord.AutocompleteContext):
        boss = ctx.options.get("boss")
        composicao = ctx.options.get("composicao")

        if not boss or not composicao:
            return []

        user_data = await self.get_user_data(ctx.interaction.user.id)
        if not user_data:
            return []

        inventory = await self.get_user_inventory(user_data["ccid"])
        boss_comps = self.comps_data.get(boss, [])

        if composicao.lower() == "meta":
            all_classes = {cls for comp in boss_comps for cls in comp["classes"]}
        else:
            comp = next((c for c in boss_comps if c["name"].lower() == composicao.lower()), None)
            if not comp:
                return []
            all_classes = set(comp["classes"])

        user_available = self.check_available_classes(list(all_classes), inventory)
        return user_available[:25]


    async def rebuild_all_raid_views(self):
        await self.bot.wait_until_ready()
        for raid_id, raid in list(self.active_raids.items()):
            if raid.get("needs_rebuild"):
                try:
                    # Recria threads para raids antigas
                    if "message_id" in raid and "thread_id" not in raid:
                        channel = self.bot.get_channel(self.raid_channel_id)
                        if channel:
                            try:
                                message = await channel.fetch_message(raid["message_id"])
                                thread = await message.create_thread(
                                    name=f"{self.THREAD_PREFIX}{raid['boss']}",
                                    auto_archive_duration=1440
                                )
                                raid["thread_id"] = thread.id
                                self.save_raid(raid_id)
                            except discord.NotFound:
                                print(f"Mensagem da raid {raid_id} não existe mais")
                                self.delete_raid(raid_id)
                    await self.rebuild_raid_view(raid_id)
                except Exception as e:
                    print(f"Erro ao reconstruir view da raid {raid_id}: {e}")
                    
    # Reconstrói a Raid
    async def rebuild_raid_view(self, raid_id: str):
        try:
            raid = self.active_raids.get(raid_id)
            if not raid or not raid.get("message_id"):
                return
                
            channel = self.bot.get_channel(self.raid_channel_id)
            if not channel:
                return
                
            message = await channel.fetch_message(raid["message_id"])
            boss_data = self.bosses_data[raid["boss"]]
            embed = self.create_raid_embed(raid, boss_data)
            
            view = RaidView(self, raid_id) if raid["status"] == "recruiting" else ConfirmationView(self, raid_id)
            await message.edit(embed=embed, view=view)
        except discord.NotFound:
            print(f"Mensagem da raid {raid_id} não encontrada, removendo...")
            self.delete_raid(raid_id)
        except Exception as e:
            print(f"Erro ao reconstruir view da raid {raid_id}: {e}")

    def save_raid(self, raid_id: str) -> None:
        if raid_id in self.active_raids:
            with open(self.raids_dir / f"{raid_id}.json", "w", encoding="utf-8") as f:
                json.dump(self.active_raids[raid_id], f, indent=4)

    def delete_raid(self, raid_id: str) -> None:
        if raid_id in self.active_raids:
            del self.active_raids[raid_id]
        path = self.raids_dir / f"{raid_id}.json"
        if path.exists():
            path.unlink()

    async def log_raid(self, raid_id: str, status: Literal["completed", "canceled", "deleted"]) -> None:
        if raid_id not in self.active_raids:
            return
            
        raid = self.active_raids[raid_id]
        log_data = {
            "boss": raid["boss"],
            "comp": raid["comp"],
            "creator": raid["creator"],
            "members": raid["members"],
            "status": status,
            "created_at": raid.get("created_at", time.time()),
            "ended_at": time.time(),
            "status": "in progress" if status == "deleted" and raid["status"] == "in progress" else status
        }
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        log_file = self.logs_dir / f"{raid_id}_{status}_{timestamp}.json"
        
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=4)

    async def get_user_data(self, user_id: int) -> Optional[Dict]:
        users_file = self.data_dir / "users.json"
        if not users_file.exists():
            return None
            
        with open(users_file, "r") as f:
            users_data = json.load(f)
            return users_data.get(str(user_id))

    async def get_user_inventory(self, ccid: str) -> List[Dict]:
        try:
            response = requests.get(
                f"https://account.aq.com/CharPage/Inventory?ccid={ccid}",
                timeout=10
            )
            return response.json()
        except Exception as e:
            print(f"Erro ao obter inventário: {e}")
            return []

    def check_available_classes(self, required_classes: List[str], inventory: List[Dict]) -> List[str]:
        # Modo Livre/Juggernaut
        if not required_classes:
            return [item["strName"] for item in inventory 
                    if item.get("strType", "").lower() == "class"]
        
        # Resto da lógica original para Meta/Composições
        user_classes = [item["strName"].lower() for item in inventory 
                    if item.get("strType", "").lower() == "class"]
        
        equivalent_map = {
            "stonecrusher": ["infinity titan"],
            "infinity titan": ["stonecrusher"]
        }
        
        available = []
        for cls in required_classes:
            cls_lower = cls.lower()
            equivalents = equivalent_map.get(cls_lower, []) + [cls_lower]
            if any(eq in user_classes for eq in equivalents):
                available.append(cls)
        
        return available

    async def get_visible_bosses(self, ctx: discord.AutocompleteContext):
        return [
            boss_name for boss_name in self.visible_bosses
            if ctx.value.lower() in boss_name.lower()
        ]


    async def cleanup_inactive_raids(self) -> None:
        while True:
            await asyncio.sleep(300)
            now = time.time()
            to_remove = []
            
            for raid_id, raid in list(self.active_raids.items()):
                if raid["status"] == "completed":
                    continue
                    
                created = raid.get("started_at" if raid["status"] == "in progress" else "created_at", now - 3601)
                if raid["status"] in ["recruiting", "in progress"] and now - created > 3600:
                    to_remove.append(raid_id)

            for raid_id in to_remove:
                try:
                    raid = self.active_raids.get(raid_id)
                    if raid:
                        # Arquivar thread
                        if "thread_id" in raid:
                            thread = self.bot.get_channel(raid["thread_id"])
                            if thread:
                                await thread.archive()
                        
                        # Deletar mensagem principal
                        if raid.get("message_id"):
                            channel = self.bot.get_channel(self.raid_channel_id)
                            if channel:
                                try:
                                    msg = await channel.fetch_message(raid["message_id"])
                                    await msg.delete()
                                except discord.NotFound:
                                    pass
                        
                        # Deletar canal de voz
                        if "voice_channel_id" in raid:
                            voice_channel = self.bot.get_channel(raid["voice_channel_id"])
                            if voice_channel:
                                await voice_channel.delete()
                        
                        # Log e remoção
                        await self.log_raid(raid_id, "canceled")
                        self.delete_raid(raid_id)
                except Exception as e:
                    print(f"Erro ao limpar raid {raid_id}: {e}")


    # Comandos de raid
    raid = SlashCommandGroup("raid", "Comandos para gerenciar raids de Ultra Bosses")

    from discord.ext.commands import cooldown, BucketType

    @raid.command(name="criar", description="Cria uma nova raid contra um Ultra Boss")
    @cooldown(1, 5, BucketType.user) # Padrão: 300 segundos
    async def criar_raid(
        self,
        ctx: discord.ApplicationContext,
        boss: Option(str, "Escolha o Ultra Boss", autocomplete=get_visible_bosses),
        composicao: Option(str, "Modo de Jogo", choices=["Meta", "Livre"]),
        classe: Option(str, "Sua classe inicial", autocomplete=autocomplete_classes)
    ):
        await ctx.defer(ephemeral=True)

        # Verificação de raids existentes
        for raid in self.active_raids.values():
            if raid["creator"] == ctx.author.id and raid["boss"] == boss and raid["status"] in ["recruiting", "confirming"]:
                return await ctx.respond("❌ Você já tem uma raid ativa para este boss!", ephemeral=True)

        user_data = await self.get_user_data(ctx.author.id)
        if not user_data:
            return await ctx.respond("❌ Você precisa se vincular primeiro!", ephemeral=True)

        inventory = await self.get_user_inventory(user_data["ccid"])
        boss_comps = self.comps_data.get(boss, [])

        party_size = self.bosses_data[boss]["party_size"]
        if composicao.lower() == "juggernaut":
            party_size = 3

        if composicao.lower() == "meta":
            all_classes = {cls for comp in boss_comps for cls in comp["classes"]}
            available_classes = sorted(list(all_classes))
            user_available = self.check_available_classes(available_classes, inventory)
            if classe not in user_available:
                return await ctx.respond("❌ Você não possui essa classe no inventário para o modo META!", ephemeral=True)

            selected_comp = {
                "name": "Meta",
                "classes": available_classes,
                "strategy": "Modo META - escolha qualquer classe das composições disponíveis."
            }
        elif composicao.lower() in ["livre", "juggernaut"]:
            all_inventory = self.check_available_classes([], inventory)
            if classe not in all_inventory:
                return await ctx.respond("❌ Você não possui essa classe!", ephemeral=True)

            selected_comp = {
                "name": composicao,
                "classes": [],
                "strategy": "Modo LIVRE - sem restrições." if composicao == "livre" else "Modo JUGGERNAUT - 3 jogadores apenas."
            }
        else:
            selected_comp = next((c for c in boss_comps if c["name"].lower() == composicao.lower()), None)
            if not selected_comp:
                return await ctx.respond("❌ Composição não encontrada!", ephemeral=True)

            user_available = self.check_available_classes(selected_comp["classes"], inventory)
            if classe not in user_available:
                return await ctx.respond("❌ Você não possui essa classe para essa composição!", ephemeral=True)

        raid_id = f"{ctx.author.id}-{int(time.time())}"
        self.active_raids[raid_id] = {
            "boss": boss,
            "comp": composicao,
            "creator": ctx.author.id,
            "status": "recruiting",
            "party_size": party_size,
            "members": {str(ctx.author.id): classe},
            "available_classes": selected_comp["classes"],
            "message_id": None,
            "strategy": selected_comp["strategy"],
            "created_at": time.time()
        }

        await self.post_raid_to_channel(raid_id)
        self.save_raid(raid_id)
        await ctx.respond(f"✅ Raid criada com sucesso em <#{self.raid_channel_id}>!", ephemeral=True)



    async def post_raid_to_channel(self, raid_id: str) -> None:
        raid = self.active_raids[raid_id]
        boss_data = self.bosses_data[raid["boss"]]
        channel = self.bot.get_channel(self.raid_channel_id)

        if not channel:
            print("Canal de raids não encontrado!")
            return

        # 1. Criar mensagem principal no canal
        main_embed = self.create_raid_embed(raid, boss_data)
        main_message = await channel.send(
            content=f"🔥 Nova raid contra {raid['boss']} criada por <@{raid['creator']}>!",
            embed=main_embed
        )

        try:
            # 2. Criar thread associada
            thread = await main_message.create_thread(
                name=f"{self.THREAD_PREFIX}{raid['boss']}",
                auto_archive_duration=1440  # Remova o 'reason'
            )
    

            await thread.send("Configurando a thread...")
            # 3. Criar embed do painel de controle na thread
            control_embed = discord.Embed(
                title=f"⚔️ {raid['boss']} - Painel de Controle",
                description=(
                    "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
                    f"**Modo:** {raid['comp']}\n"
                    f"**Status:** {raid['status'].capitalize()}\n"
                    f"**Slots:** {len(raid['members'])}/{raid['party_size']}\n"
                    "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
                ),
                color=discord.Color.gold()
            )

            # Adicionar participantes
            participants = "\n".join(
                [f"<@{uid}> - `{cls}`" for uid, cls in raid['members'].items()]
            ) or "Nenhum participante"
            
            control_embed.add_field(
                name="Participantes",
                value=participants,
                inline=False
            )

            # 4. Enviar mensagem fixa com botões
            control_message = await thread.send(
                embed=control_embed,
                view=ThreadRaidView(self, raid_id)
            )
            await control_message.pin()

            # 5. Atualizar dados da raid
            raid["thread_id"] = thread.id
            raid["message_id"] = main_message.id
            self.save_raid(raid_id)

            #raid["message_id"] = main_message.id
            #raid["thread_id"] = thread.id
            #self.save_raid(raid_id)  # Salve imediatamente!
            
            
            # 6. Notificar líder para seleção de classe
            #leader_data = await self.get_user_data(raid["creator"])
            #if leader_data:
            #    inventory = await self.get_user_inventory(leader_data["ccid"])
            #    available_classes = self._get_dynamic_available_classes(raid)
            #    user_available = self.check_available_classes(available_classes, inventory)

            #    if user_available:
            #        view = ClassSelectView(
            #            user_available=user_available,
            #            raid_id=raid_id,
            #            cog=self,
            #            target_user_id=raid["creator"]
            #        )
            #        await thread.send(
            #            f"👑 <@{raid['creator']}>, **selecione sua classe primeiro!**",
            #            view=view
            #        )

            # 7. Atualizar mensagem principal com botão de link
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                label="Ir para a Thread",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/channels/{channel.guild.id}/{thread.id}"
            ))
            await main_message.edit(view=view)


        except Exception as e:
            print(f"Erro ao criar thread: {str(e)}")
            await main_message.reply("⚠️ Falha ao configurar a thread da raid!")
            self.delete_raid(raid_id)

    def create_raid_embed(self, raid: RaidData, boss_data: BossData) -> discord.Embed:
        from datetime import datetime

        # Expiração da raid
        expires_at = int(raid["created_at"]) + 3600
        created_str = f"<t:{int(raid['created_at'])}:R>"
        expires_str = f"<t:{expires_at}:R>"

        # Participantes formatados como slots fixos (4, por padrão)
        party_size = raid["party_size"]
        members = list(raid["members"].items())
        participantes = []
        for i in range(party_size):
            if i < len(members):
                uid, cls = members[i]
                participantes.append(f"<@{uid}> — `{cls}`")
            else:
                participantes.append("-")


        # Corrigir lógica de classes disponíveis
        if raid["comp"].lower() in ["livre", "juggernaut"]:
            available = ["Qualquer Classe"]
        else:
            available = self._get_dynamic_available_classes(raid)



        # Classes disponíveis (não escolhidas ainda)
        # taken = set(raid["members"].values())
        # available = [cls for cls in raid["available_classes"] if cls not in taken]

        # Cria embed com o estilo compacto
        embed = discord.Embed(
            title=raid["boss"],
            url=boss_data.get("doc_url", ""),
            description=(
                f"🗺️ **Mapa:** `{boss_data['map']}`\n"
                f"⚡ **Dificuldade:** `{boss_data['difficulty']}`\n"
                f"👑 **Criador:** <@{raid['creator']}>\n"
                f"📅 **Criada:** {created_str}\n"
                f"⏳ **Expiração:** {expires_str}"
            ),
            colour=discord.Color.blue(),
            timestamp=datetime.now()
        )

        if boss_data.get("thumbnail_url"):
            embed.set_thumbnail(url=boss_data["thumbnail_url"])

        embed.add_field(
            name="CLASSES DISPONÍVEIS",
            value="\n".join(f"• {cls}" for cls in available) if available else "*Nenhuma*",
            inline=True
        )

        embed.add_field(
            name=f"PARTICIPANTES ({len(raid['members'])}/{party_size})",
            value="\n".join(participantes),
            inline=True
        )

        if raid.get("strategy"):
            embed.add_field(
                name="DICAS",
                value=raid["strategy"],
                inline=False
            )

        embed.set_footer(
            text="UltraHub Raid System",
            icon_url=boss_data.get("icon_url", "")
        )

        return embed


    async def update_raid_log(self, raid_id: str, action: str, user: discord.User = None, class_name: str = None, confirm_count: int = None):
        raid = self.active_raids.get(raid_id)
        if not raid or "thread_id" not in raid:
            return

        thread = self.bot.get_channel(raid["thread_id"])
        if not thread:
            return

        try:
            # Busca a última mensagem de log na thread
            async for message in thread.history(limit=10):
                if message.embeds and message.embeds[0].title == "📜 Log da Raid":
                    current_content = message.embeds[0].description.strip("`\n")
                    break
            else:
                current_content = ""
            
            new_line = ""
            if action == "join_attempt":
                new_line = f"[{datetime.now().strftime('%H:%M')}] @{user.name} está tentando entrar na raid!"
            elif action == "join_success":
                new_line = f"[{datetime.now().strftime('%H:%M')}] @{user.name} entrou na raid como {class_name}!"
            elif action == "confirm_update":
                new_line = f"[{datetime.now().strftime('%H:%M')}] {confirm_count}/{raid['party_size']} presenças confirmadas"
            
            new_content = f"```\n{current_content}\n{new_line}\n```"
            
            embed = discord.Embed(
                title="📜 Log da Raid",
                description=new_content,
                color=discord.Color.blurple()
            )
            embed.set_footer(text="UltraHub Raid System")
            
            # Edita a mensagem existente ou cria uma nova se não encontrar
            if 'message' in locals():
                await message.edit(embed=embed)
            else:
                await thread.send(embed=embed)
                
        except Exception as e:
            print(f"Erro ao atualizar log da raid: {e}")


    async def update_thread_control_panel(self, raid_id: str):
        raid = self.active_raids.get(raid_id)
        if not raid or "thread_id" not in raid:
            return

        thread = self.bot.get_channel(raid["thread_id"])
        if not thread:
            return

        # Buscar mensagem fixada
        pinned = await thread.pins()
        control_message = next((msg for msg in pinned if msg.embeds and "Painel de Controle" in msg.embeds[0].title), None)

        if control_message:
            # Atualizar embed
            new_embed = control_message.embeds[0].copy()
            
            # Atualizar participantes
            participants = "\n".join(
                [f"<@{uid}> - `{cls}`" for uid, cls in raid['members'].items()]
            ) or "Nenhum participante"
            
            new_embed.set_field_at(
                0,
                name=new_embed.fields[0].name,
                value=participants,
                inline=False
            )
            
            # Atualizar status e slots
            new_embed.description = (
                "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
                f"**Modo:** {raid['comp']}\n"
                f"**Status:** {raid['status'].capitalize()}\n"
                f"**Slots:** {len(raid['members'])}/{raid['party_size']}\n"
                "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
            )
            
            await control_message.edit(embed=new_embed)

    async def update_raid_message(self, raid_id: str) -> None:
        raid = self.active_raids.get(raid_id)
        await self.update_thread_control_panel(raid_id) 

        if not raid or not raid["message_id"]:
            return
        
        channel = self.bot.get_channel(self.raid_channel_id)
        if not channel:
            return

        if raid["comp"].lower() == "juggernaut" and len(raid["members"]) >= 3:
            raid["status"] = "confirming"
            await self.update_raid_log(raid_id, "party_full")

        try:
            message = await channel.fetch_message(raid["message_id"])
            boss_data = self.bosses_data[raid["boss"]]
            embed = self.create_raid_embed(raid, boss_data)
            
            view = (
                RaidView(self, raid_id) 
                if raid["status"] == "recruiting" 
                else ConfirmationView(self, raid_id)            
            )        
            
            await message.edit(embed=embed, view=view)
            self.save_raid(raid_id)

            if len(raid["members"]) >= raid["party_size"] and raid["status"] != "confirming":
                raid["status"] = "confirming"
                
                # ✅ Verifica se confirmação já foi enviada
                if not raid.get("confirmation_sent"):
                    if "thread_id" in raid:
                        thread = self.bot.get_channel(raid["thread_id"])
                        if thread:
                            view = ConfirmationView(self, raid_id)
                            confirm_embed = discord.Embed(
                                title="🔔 CONFIRMAÇÃO URGENTE 🔔",
                                description="Você tem **5 minutos** para confirmar presença!\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
                                color=discord.Color.orange()
                            )

                            # Mencionar todos os participantes
                            mentions = " ".join(f"<@{uid}>" for uid in raid["members"])
                            confirm_msg = await thread.send(content=mentions, embed=confirm_embed, view=view)
                            await confirm_msg.pin()
                            view.message = confirm_msg

                    # Marcar como enviada
                    raid["confirmation_sent"] = True
                    self.save_raid(raid_id)

                        
        except Exception as e:
            print(f"Erro ao atualizar mensagem da raid {raid_id}: {e}")

    @raid.command(name="listar", description="Mostra raids disponíveis para o boss que você pode entrar.")
    async def listar_raids(
        self,
        ctx: discord.ApplicationContext,
        boss: Option(str, "Nome do Ultra Boss", choices=["Ultra Warden", "Ultra Engineer", "Ultra Drago", "Champion Drakath", "Ultra Darkon", "Ultra Speaker"])
    ):
        user_data = await self.get_user_data(ctx.author.id)
        if not user_data:
            return await ctx.respond("❌ Você precisa se vincular primeiro!", ephemeral=True)
            
        inventory = await self.get_user_inventory(user_data["ccid"])
        user_classes = [
            item["strName"].lower() 
            for item in inventory 
            if item.get("strType", "").lower() == "class"
        ]

        matching_raids = []
        for rid, raid in self.active_raids.items():
            if raid["boss"] != boss or raid["status"] != "recruiting":
                continue
                
            available = [
                cls for cls in raid["available_classes"] 
                if cls.lower() in user_classes and 
                cls not in raid["members"].values()
            ]
            
            if available:
                matching_raids.append((rid, raid, available))

        if not matching_raids:
            return await ctx.respond("❌ Nenhuma raid disponível para você nesse boss. Verifique se as classes estão no inventário.", ephemeral=True)

        embed = discord.Embed(
            title=f"📋 Raids disponíveis: {boss}", 
            color=discord.Color.blue()
        )
        
        for rid, raid, classes in matching_raids:
            embed.add_field(
                name=f"Raid ID: `{rid}` — Criador: <@{raid['creator']}>",
                value=f"Classes possíveis: {', '.join(classes)}",
                inline=False
            )

        await ctx.respond(embed=embed, ephemeral=True)

    @raid.command(name="sair", description="Sai de uma ou todas as raids.")
    async def sair_raid(
        self,
        ctx: discord.ApplicationContext,
        raid_id: Option(str, "ID da raid para sair (deixe vazio para sair de todas)", required=False)
    ):
        user_id = str(ctx.author.id)
        saiu = False
        
        if raid_id:
            if raid_id not in self.active_raids:
                return await ctx.respond("❌ Raid não encontrada.", ephemeral=True)
                
            if user_id in self.active_raids[raid_id]["members"]:
                del self.active_raids[raid_id]["members"][user_id]
                await self.update_raid_message(raid_id)
                self.save_raid(raid_id)
                saiu = True
        else:
            for rid in list(self.active_raids):
                if user_id in self.active_raids[rid]["members"]:
                    del self.active_raids[rid]["members"][user_id]
                    await self.update_raid_message(rid)
                    self.save_raid(rid)
                    saiu = True
                    
        if saiu:
            await ctx.respond("✅ Você saiu da(s) raid(s) com sucesso!", ephemeral=True)
        else:
            await ctx.respond("❌ Você não está em nenhuma raid.", ephemeral=True)

    @raid.command(name="remover", description="Remove um jogador da sua raid (apenas líderes)")
    async def remover_jogador(
        self,
        ctx: discord.ApplicationContext,
        raid_id: Option(str, "ID da raid"),
        usuario: Option(discord.Member, "Usuário para remover")
    ):
        await ctx.defer(ephemeral=True)
        
        raid = self.active_raids.get(raid_id)
        if not raid:
            return await ctx.respond("❌ Raid não encontrada!", ephemeral=True)
            
        if raid["creator"] != ctx.author.id:
            return await ctx.respond("❌ Apenas o líder pode remover jogadores!", ephemeral=True)
            
        if str(usuario.id) not in raid["members"]:
            return await ctx.respond("❌ Este usuário não está na raid!", ephemeral=True)
            
        del raid["members"][str(usuario.id)]
        await self.update_raid_message(raid_id)
        self.save_raid(raid_id)
        
        # Notificar na thread
        if "thread_id" in raid:
            thread = self.bot.get_channel(raid["thread_id"])
            if thread:
                await thread.send(f"🚫 <@{usuario.id}> foi removido da raid por <@{ctx.author.id}>")
        
        await ctx.respond(f"✅ {usuario.mention} foi removido com sucesso!", ephemeral=True)

    @raid.command(name="deletar", description="Deleta uma raid que você criou")
    async def deletar_raid(self, ctx: discord.ApplicationContext):
        user_raids = [
            (raid_id, raid) 
            for raid_id, raid in self.active_raids.items()
            if raid["creator"] == ctx.author.id 
            and raid["status"] in ["recruiting", "confirming", "in progress"]
        ]
        
        if not user_raids:
            return await ctx.respond("❌ Você não tem nenhuma raid ativa para deletar.", ephemeral=True)
            
        if not user_raids:
            return await ctx.respond("❌ Nenhuma raid ativa encontrada.", ephemeral=True)        
        # Criar a view com o dropdown
        view = View()
        select = Select(
            placeholder="Selecione a raid para deletar",
            options=[
                discord.SelectOption(
                    label=f"{raid['boss']} ({raid['comp']}) - {len(raid['members'])}/{raid['party_size']} membros",
                    value=raid_id,
                    description=f"ID: {raid_id}"
                )
                for raid_id, raid in user_raids
            ]
        )
        view.add_item(select)
        
        # Enviar a mensagem com o dropdown
        message = await ctx.respond(
            "🛑 Selecione a raid que deseja deletar:",
            view=view,
            ephemeral=True
        )
        
        # Definir o callback para quando uma opção for selecionada
        async def select_callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("❌ Apenas o criador pode deletar esta raid.", ephemeral=True)
            
            raid_id = select.values[0]
            raid = self.active_raids.get(raid_id)
            
            if not raid:
                return await interaction.response.send_message("❌ Raid não encontrada.", ephemeral=True)
                
            try:
                channel = self.bot.get_channel(self.raid_channel_id)
                if channel and raid["message_id"]:
                    msg = await channel.fetch_message(raid["message_id"])
                    await msg.delete()
            except Exception as e:
                print(f"Erro ao deletar mensagem da raid: {e}")

            # Após deletar a mensagem principal:
            if "thread_id" in raid:
                try:
                    thread = self.bot.get_channel(raid["thread_id"])
                    if thread:
                        await thread.archive()  # Ou await thread.delete()
                except Exception as e:
                    print(f"Erro ao arquivar thread: {e}")                
                
            await self.log_raid(raid_id, "deleted")
            self.delete_raid(raid_id)
            
            # Atualizar a mensagem original para mostrar que foi deletado
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                content=f"✅ Raid **{raid['boss']}** deletada com sucesso!",
                view=None
            )
        
        select.callback = select_callback



    async def handle_raid_completion(self, raid_id: str):
        raid = self.active_raids.get(raid_id)
        if not raid:
            return

        # Salvar o status final antes de deletar
        if raid["status"] != "completed":
            raid["status"] = "completed"
            self.save_raid(raid_id)

        # Registrar log antes de deletar
        await self.log_raid(raid_id, "completed")

        # Deletar mensagem principal
        if raid.get("message_id"):
            try:
                channel = self.bot.get_channel(self.raid_channel_id)
                msg = await channel.fetch_message(raid["message_id"])
                await msg.delete()
            except:
                pass

        # Arquivar thread
        if "thread_id" in raid:
            thread = self.bot.get_channel(raid["thread_id"])
            if thread:
                await thread.archive()

        # Deletar canal de voz
        if "voice_channel_id" in raid:
            voice_channel = self.bot.get_channel(raid["voice_channel_id"])
            if voice_channel:
                await voice_channel.delete()

        # Remover dos registros
        self.delete_raid(raid_id)


    async def voice_channel_timeout(self, raid_id: str):
        await asyncio.sleep(3600)  # 1 hora
        raid = self.active_raids.get(raid_id)
        if raid and raid["status"] == "in progress":
            await self.log_raid(raid_id, "canceled")
            self.delete_raid(raid_id)
            # Adicione aqui a lógica para notificar e arquivar

class RaidView(View):
    def __init__(self, cog: RaidSystem, raid_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.raid_id = raid_id
        
        # Botão de link dinâmico
        raid = cog.active_raids.get(raid_id)

        if raid and raid.get("thread_id"):
            self.add_item(
                Button(
                    label="Join Raid",  # Espada + texto
                    style=discord.ButtonStyle.link,
                    url=f"https://discord.com/channels/{cog.bot.guilds[0].id}/{raid['thread_id']}",
                    row=0,
                    emoji="⚔️"  # Opcional - funciona junto com o label
                )
            )        
        #self.add_item(JoinRaidButton(raid_id))
    async def on_timeout(self):
        # Garantir que a view não seja removida automaticamente
        pass    

class ThreadRaidView(View):
    def __init__(self, cog: RaidSystem, raid_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.raid_id = raid_id
        self.add_item(ThreadJoinButton(cog, raid_id)) 
        
        # Botões principais
      
        self.add_item(SwapClassButton(raid_id))
        self.add_item(LeaveRaidButton(raid_id))
        self.add_item(RaidHelpButton()) 

    #if not any(isinstance(child, ConfirmButton) for child in self.children):
    #    self.add_item(ConfirmButton(...))

    async def update_buttons(self):
        """Atualiza estado dos botões baseado no usuário"""
        raid = self.cog.active_raids.get(self.raid_id)
        user_id = self.ctx.author.id if self.ctx else None
        
        # Desabilitar Trocar Classe se não tiver selecionado
        for item in self.children:
            if isinstance(item, SwapClassButton):
                item.disabled = (str(user_id) not in raid["members"] or raid["members"].get(str(user_id)) == "PENDING")



class ThreadJoinButton(Button):
    def __init__(self, cog: RaidSystem, raid_id: str):
        super().__init__(
            label="Entrar na Raid", 
            style=discord.ButtonStyle.green,
            emoji="🛡️"
        )
        self.cog = cog
        self.raid_id = raid_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raid = self.cog.active_raids.get(self.raid_id)
        
        # Verificações iniciais
        if not raid:
            return await interaction.followup.send(
                "❌ Raid não encontrada!", 
                ephemeral=True
            )

        if raid["status"] != "recruiting":
            return await interaction.followup.send(
                "❌ Esta raid não está mais recrutando!", 
                ephemeral=True
            )

        if str(interaction.user.id) in raid["members"]:
            return await interaction.followup.send(
                "❌ Você já está nesta raid!", 
                ephemeral=True
            )

        # Verificar vinculação de conta
        user_data = await self.cog.get_user_data(interaction.user.id)
        if not user_data:
            return await interaction.followup.send(
                "❌ Você precisa se vincular primeiro!", 
                ephemeral=True
            )

        # Verificar classes disponíveis
        inventory = await self.cog.get_user_inventory(user_data["ccid"])
        available_classes = self.cog._get_dynamic_available_classes(raid)
        user_available = self.cog.check_available_classes(available_classes, inventory)

        if not user_available:
            return await interaction.followup.send(
                "❌ Você não possui nenhuma das classes disponíveis!", 
                ephemeral=True
            )

        # Enviar seletor de classe na thread
        view = ClassSelectView(
            user_available=user_available,
            raid_id=self.raid_id,
            cog=self.cog,
            target_user_id=interaction.user.id
        )

        await interaction.followup.send(
            f"🛡️ Selecione sua classe para **{raid['boss']}**:",
            view=view,
            ephemeral=True
        )


        thread = self.cog.bot.get_channel(raid["thread_id"])
        if thread:
            await thread.send(
                f"🎉 <@{interaction.user.id}> está selecionando uma classe..."
            )
            
        # Atualizar log da raid
        await self.cog.update_raid_log(
            self.raid_id, 
            "join_attempt", 
            user=interaction.user
        )
        
class SwapClassButton(Button):
    def __init__(self, raid_id: str):
        super().__init__(label="Trocar Classe", style=discord.ButtonStyle.blurple, emoji="🔄")
        self.raid_id = raid_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cog = self.view.cog
        raid = cog.active_raids.get(self.raid_id)
        user_id = str(interaction.user.id)

        if not raid or user_id not in raid["members"] or raid["members"][user_id] == "PENDING":

            return await interaction.followup.edit_message(
                message_id=interaction.message.id,
                content=f"❌ Você ainda não selecionou nenhuma classe!",
                view=None,
                ephemeral=True
            )
            # return await interaction.response.send_message("❌ Você ainda não selecionou nenhuma classe!", ephemeral=True)

        user_data = await cog.get_user_data(interaction.user.id)
        if not user_data:

            return await interaction.followup.edit_message(
                message_id=interaction.message.id,
                content=f"❌ Você precisa se vincular primeiro!",
                view=None,
                ephemeral=True
            )
            #return await interaction.response.send_message("❌ Você precisa se vincular primeiro!", ephemeral=True)

        inventory = await cog.get_user_inventory(user_data["ccid"])
        available_classes = cog._get_dynamic_available_classes(raid)
        user_available = cog.check_available_classes(available_classes, inventory)

        if not user_available:

            return await interaction.followup.edit_message(
                message_id=interaction.message.id,
                content=f"❌ Você não possui nenhuma das classes disponíveis!",
                view=None,
                ephemeral=True
            )            
            # return await interaction.response.send_message("❌ Você não possui nenhuma das classes disponíveis!", ephemeral=True)

        view = ClassSelectView(
            user_available=user_available,
            raid_id=self.raid_id,
            cog=cog,
            target_user_id=interaction.user.id
        )

        thread = cog.bot.get_channel(raid["thread_id"])
        if thread:
            await interaction.followup.send(
                "🔄 Selecione uma nova classe:",
                view=view,
                ephemeral=True
            )


class LeaveRaidButton(Button):
    def __init__(self, raid_id: str):
        super().__init__(style=discord.ButtonStyle.red, label="Sair", custom_id=f"leave_{raid_id}")
        self.raid_id = raid_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cog = self.view.cog
        user_id = str(interaction.user.id)
        raid = cog.active_raids.get(self.raid_id)

        if not raid or user_id not in raid["members"]:
            return await interaction.followup.send("❌ Você não está nesta raid!", ephemeral=True)

        if not raid:
            return await interaction.followup.send("❌ Raid não encontrada!", ephemeral=True)
            
        # Bloquear saída durante confirmação/progresso
        if raid["status"] in ["confirming", "in progress"]:
            return await interaction.followup.send(
                "❌ Não é possível sair durante a confirmação ou progresso da raid!",
                ephemeral=True
            )

        if user_id == str(raid["creator"]):
            if len(raid["members"]) == 1:
                # Só o líder está na raid — encerrar completamente
                if raid.get("message_id"):
                    try:
                        channel = cog.bot.get_channel(cog.raid_channel_id)
                        msg = await channel.fetch_message(raid["message_id"])
                        await msg.delete()
                    except:
                        pass

                if "thread_id" in raid:
                    try:
                        thread = cog.bot.get_channel(raid["thread_id"])
                        await thread.archive()
                    except:
                        pass

                if "voice_channel_id" in raid:
                    try:
                        vc = cog.bot.get_channel(raid["voice_channel_id"])
                        await vc.delete()
                    except:
                        pass

                await cog.log_raid(self.raid_id, "canceled")
                cog.delete_raid(self.raid_id)
                return await interaction.followup.send("👑 Raid encerrada porque o líder saiu.", ephemeral=True)
            else:
                # Transferir liderança para outro membro
                remaining_members = [uid for uid in raid["members"] if uid != user_id]
                new_leader = remaining_members[0]
                raid["creator"] = new_leader
                await cog.log_raid(self.raid_id, f"ownership_transferred:{user_id}->{new_leader}")
                await interaction.followup.send(f"👑 A liderança foi transferida para <@{new_leader}>.", ephemeral=True)

        # Remover membro
        del raid["members"][user_id]
        await cog.update_raid_message(self.raid_id)
        cog.save_raid(self.raid_id)
        await interaction.followup.send("✅ Você saiu da raid!", ephemeral=True)



class RaidHelpButton(Button):
    def __init__(self):
        super().__init__(
            label="Ajuda",  # <--- Parâmetro adicionado
            style=discord.ButtonStyle.secondary,
            emoji="❓"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="📘 Comandos da Raid",
            description=(
                "```diff\n"
                "+ ENTRAR NA RAID\n"
                "- Use o botão verde para selecionar uma classe\n"
                "+ TROCAR CLASSE\n"
                "- Disponível após entrar na raid (botão azul)\n"
                "+ SAIR DA RAID\n"
                "- Remove você da party (botão vermelho)\n"
                "```"
            ),
            color=discord.Color.blurple()
        )
        
        await interaction.followup.send(
                "",
                embed=embed,
                ephemeral=True
            )        
        # await interaction.response.send_message(embed=embed, ephemeral=True)

class SeeRaidButton(Button):
    def __init__(self, raid_id: str):
        super().__init__(
            label="Ver Raid",
            style=discord.ButtonStyle.link,
            emoji="🛡️",
            url=thread_url  # Definiremos depois
        )
        self.raid_id = raid_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        pass  # Nada aqui, pois o botão é do tipo LINK

class JoinRaidButton(Button):
    def __init__(self, raid_id: str):
        super().__init__(
            label="Entrar na Raid",
            style=discord.ButtonStyle.green,
            emoji="🛡️"
        )
        self.raid_id = raid_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raid_id = self.raid_id
        cog = self.view.cog
        raid = self.view.cog.active_raids.get(self.raid_id)
        
        # Permitir que o líder ignore a verificação de PENDING
        if interaction.user.id != raid["creator"]:  # Apenas para não-líderes
            if raid["members"].get(str(raid["creator"])) == "PENDING":
                return await interaction.response.send_message(
                    "⏳ Aguarde o líder escolher sua classe primeiro!", 
                    ephemeral=True, 
                    delete_after=8
                )

        if interaction.user.id in cog.pending_selections:
            return await interaction.response.send_message("⌛ Você já está selecionando uma classe!", ephemeral=True)
        cog.pending_selections.add(interaction.user.id)

        if not raid:
            return await interaction.response.send_message("❌ Raid não encontrada!", ephemeral=True, delete_after=8)

        if raid["status"] != "recruiting":
            return await interaction.response.send_message("❌ Esta raid não está mais recrutando!", ephemeral=True, delete_after=8)

        if str(interaction.user.id) in raid["members"]:
            return await interaction.response.send_message("❌ Você já está nesta raid!", ephemeral=True, delete_after=8)

        user_data = await cog.get_user_data(interaction.user.id)
        if not user_data:
            return await interaction.response.send_message("❌ Você precisa se vincular primeiro!", ephemeral=True, delete_after=8)

        inventory = await cog.get_user_inventory(user_data["ccid"])
        available_classes = cog._get_dynamic_available_classes(raid)
        user_available = cog.check_available_classes(available_classes, inventory)
       
        if not user_available:
            return await interaction.response.send_message("❌ Você não possui nenhuma das classes disponíveis no seu inventário!", ephemeral=True, delete_after=8)

        # Envia mensagem na thread com seletor de classe
        if "thread_id" in raid:
            thread = cog.bot.get_channel(raid["thread_id"])
            if thread:
                #await thread.send(f"<@{interaction.user.id}> está tentando entrar na raid!")
                await cog.update_raid_log(raid_id, "join_attempt", user=interaction.user)

                view = ClassSelectView(
                    user_available=user_available,
                    raid_id=raid_id,
                    cog=cog,
                    target_user_id=interaction.user.id  # Parâmetro adicionado
                )

                await thread.send(f"🛡️ <@{interaction.user.id}>, selecione sua classe para **{raid['boss']}**:", view=view)
                await interaction.response.send_message(f"🔁 Vá até a thread da raid para escolher sua classe: {thread.jump_url}", ephemeral=True, delete_after=12)
            else:
                await interaction.response.send_message("❌ Thread da raid não encontrada.", ephemeral=True, delete_after=8)
        else:
            await interaction.response.send_message("❌ A raid não possui uma thread vinculada.", ephemeral=True, delete_after=8)

class ClassSelectView(View):
    def __init__(self, user_available: List[str], raid_id: str, cog: RaidSystem, target_user_id: int):
        super().__init__(timeout=120)
        self.raid_id = raid_id
        self.cog = cog
        self.target_user_id = target_user_id
        self.user_available = user_available
        self.current_page = 0
        self.pages = []

        boss_name = cog.active_raids[raid_id]["boss"]
        self.boss_comps = [set(comp["classes"]) for comp in cog.comps_data.get(boss_name, [])]
        self.selected_classes = set(cog.active_raids[raid_id]["members"].values())
        self.valid_classes = cog._get_dynamic_available_classes(cog.active_raids[raid_id])


        # Paginação para modos Livre/Juggernaut
        if self._is_free_mode():
            self.pages = [self.valid_classes[i:i+25] for i in range(0, len(self.valid_classes), 25)]
        else:
            self.pages = [self.valid_classes]

        self._update_components()

    def _is_free_mode(self) -> bool:
        raid = self.cog.active_raids[self.raid_id]
        return raid["comp"].lower() in ["livre", "juggernaut"]

    def _calculate_valid_classes(self) -> List[str]:
        raid = self.cog.active_raids[self.raid_id]
        boss_comps = self.cog.comps_data.get(raid["boss"], [])
        selected = set(raid["members"].values())
        
        valid = set()
        
        if raid["comp"].lower() == "meta":
            for comp in boss_comps:
                comp_classes = set(comp["classes"])
                if selected.issubset(comp_classes):
                    valid.update(comp_classes - selected)
        else:
            comp = next((c for c in boss_comps if c["name"].lower() == raid["comp"].lower()), None)
            if comp:
                comp_classes = set(comp["classes"])
                if selected.issubset(comp_classes):
                    valid.update(comp_classes - selected)
        
        # Filtrar apenas classes que o usuário possui
        return [cls for cls in valid if cls in self.user_available and cls not in self.selected_classes]


    def _update_components(self):
        self.clear_items()
        
        # Adicionar dropdown da página atual
        current_options = self.pages[self.current_page]
        if current_options:
            self.add_item(ClassSelect(current_options))
        else:
            self.add_item(Button(label="Nenhuma classe disponível", disabled=True))

        # Adicionar controles de paginação se necessário
        if len(self.pages) > 1:
            self.add_item(Button(
                style=discord.ButtonStyle.grey,
                label="◀",
                custom_id="prev_page",
                disabled=self.current_page == 0
            ))
            self.add_item(Button(
                style=discord.ButtonStyle.grey,
                label="▶",
                custom_id="next_page",
                disabled=self.current_page == len(self.pages)-1
            ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") in ["prev_page", "next_page"]:
            if interaction.data["custom_id"] == "prev_page":
                self.current_page = max(0, self.current_page - 1)
            else:
                self.current_page = min(len(self.pages)-1, self.current_page + 1)
            
            self._update_components()
            
            await interaction.response.edit_message(view=self)
            return False
        return interaction.user.id == self.target_user_id
    
class ClassSelect(Select):
    def __init__(self, options: List[str]):
        super().__init__(
            placeholder="Selecione sua classe...",
            options=[discord.SelectOption(label=cls, value=cls) for cls in options],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raid_id = self.view.raid_id
        cog = self.view.cog
        raid = cog.active_raids[raid_id]
        self.view.cog.pending_selections.discard(interaction.user.id)

        # Verificação reforçada do inventário
        user_data = await cog.get_user_data(interaction.user.id)
        if not user_data:
            return await interaction.followup.send("❌ Dados do usuário não encontrados!", ephemeral=True)
        
        inventory = await cog.get_user_inventory(user_data["ccid"])
        available_now = cog.check_available_classes([self.values[0]], inventory)
        
        if not available_now:
            return await interaction.followup.send(
                "❌ Você não possui mais esta classe! Atualize seu inventário.",
                ephemeral=True
            )

        # Verificar se classe ainda está válida para a composição atual
        valid_now = cog._get_dynamic_available_classes(raid)
        if self.values[0] not in valid_now:
            return await interaction.response.send_message(
                "❌ Esta classe não é mais válida após outras seleções!",
                ephemeral=True,
                delete_after=8
            )

        # Verificar se já foi escolhida
        if self.values[0] in raid["members"].values():
            return await interaction.response.send_message(
                "❌ Classe já selecionada por outro jogador!",
                ephemeral=True,
                delete_after=8
            )

            
        raid["members"][str(interaction.user.id)] = self.values[0]

        await interaction.followup.send(
            f"✅ Classe **{self.values[0]}** selecionada com sucesso!",
            ephemeral=True
        )        
        # Atualização imediata do embed
        await cog.update_raid_message(raid_id)  # ← Linha crítica
        
        raid["available_classes"] = self.view.cog._get_dynamic_available_classes(raid)
        await cog.update_raid_message(raid_id)
        
        await interaction.followup.send(
            f"✅ Você entrou como **{self.values[0]}**!",
            ephemeral=True
        )
        try:
            await interaction.message.delete()
        except:
            pass        

class ConfirmationView(View):
    def __init__(self, cog: RaidSystem, raid_id: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.raid_id = raid_id
        self.confirmed: Set[int] = set()
        


    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirm_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            user_id = interaction.user.id
            raid = self.cog.active_raids.get(self.raid_id)

            if not raid:
                return await interaction.response.send_message("❌ Raid não encontrada!", ephemeral=True)

            if str(user_id) not in raid["members"]:
                return await interaction.response.send_message("❌ Você não faz parte dessa raid!", ephemeral=True)

            if user_id in self.confirmed:
                return await interaction.response.send_message("✅ Você já confirmou presença!", ephemeral=True)

            self.confirmed.add(user_id)
            confirm_count = len(self.confirmed)

            await self.cog.update_raid_log(
                self.raid_id,
                "confirm_update",
                user=interaction.user,
                confirm_count=confirm_count
            )

            # Listar membros faltantes
            all_members = set(map(int, raid["members"].keys()))
            missing = all_members - self.confirmed
            missing_mentions = [f"<@{uid}>" for uid in missing]

            await interaction.response.send_message(
                f"✅ Presença confirmada! ({confirm_count}/{raid['party_size']})\n"
                f"🕒 Faltam: {', '.join(missing_mentions) if missing else 'Todos confirmaram!'}",
                ephemeral=True
            )
            if confirm_count >= raid['party_size']:
                await self.finalize_raid()

        except Exception as e:
            print(f"Erro no botão de confirmação: {e}")


    async def finalize_raid(self):
        raid = self.cog.active_raids.get(self.raid_id)
        if not raid:
            return

        raid["status"] = "in progress"
        raid["started_at"] = time.time()
        self.cog.save_raid(self.raid_id)

        if "thread_id" in raid:
            thread = self.cog.bot.get_channel(raid["thread_id"])
            if thread:
                boss_data = self.cog.bosses_data.get(raid["boss"], {})
                mapa = boss_data.get("map", "???")

                if "instance_number" not in raid:
                    raid["instance_number"] = random.randint(1000, 99999)
                    self.cog.save_raid(self.raid_id)

                    members = [f"<@{uid}>" for uid in raid["members"]]
                    content = f"🚀 {', '.join(members)} Preparem-se para a batalha!"

                    embed = discord.Embed(
                        title=f"RAID INICIADA: {raid['boss']}",
                        description=(
                            "**Todos os membros confirmaram!**\n\n"
                            f"🗺️ **Servidor:** SAFIRIA\n"
                            f"🗺️ **Mapa:** ```/join {mapa}-{raid['instance_number']}```\n"
                            f"⏳ **Horário:** <t:{int(time.time())}:R>"
                        ),
                        color=0x00ff00
                    )
                    if boss_data.get("thumbnail_url"):
                        embed.set_thumbnail(url=boss_data["thumbnail_url"])

                    await thread.send(content=content, embed=embed, view=CompleteView(self.cog, self.raid_id))

                # Criar canal de voz
                voice_channel = await thread.guild.create_voice_channel(
                    name=f"⚔️ {raid['boss']}",
                    category=thread.category,
                    user_limit=raid["party_size"],
                    overwrites={
                        thread.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        **{
                            thread.guild.get_member(int(uid)): discord.PermissionOverwrite(view_channel=True)
                            for uid in raid["members"]
                        }
                    }
                )
                raid["voice_channel_id"] = voice_channel.id

                msg = await thread.send(
                    f"🔊 **Entre no Canal de voz:** {voice_channel.mention}\n"
                )
                await msg.pin()

        # ✅ Atualiza mensagens
        await self.cog.update_raid_message(self.raid_id)

        await self.cog.log_raid(self.raid_id, "in progress")
        
class CompleteView(View):
    def __init__(self, cog: RaidSystem, raid_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.raid_id = raid_id
        self.add_item(CompleteButton(raid_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        raid = self.cog.active_raids.get(self.raid_id)
        if not raid:
            await interaction.response.send_message("❌ Esta raid não existe mais!", ephemeral=True)
            return False
        return interaction.user.id == raid["creator"]


class CompleteButton(Button):
    def __init__(self, raid_id: str):
        super().__init__(
            style=discord.ButtonStyle.red,
            label="Marcar como Concluída"
        )
        self.raid_id = raid_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cog = self.view.cog
        raid = cog.active_raids.get(self.raid_id)
        
        try:
            # Verificação básica da raid
            if not raid:
                return await interaction.followup.send("❌ Esta raid não existe mais!", ephemeral=True)

            # Verificar permissões do líder
            if interaction.user.id != raid["creator"]:
                return await interaction.followup.send("❌ Apenas o líder pode concluir a raid!", ephemeral=True)

            # Atualizar estado primeiro
            raid["status"] = "completed"
            cog.save_raid(self.raid_id)  # Persistir imediatamente

            # Registrar log antes de qualquer limpeza
            await cog.log_raid(self.raid_id, "completed")

            # Processar canal de voz
            voice_mention = ""
            if "voice_channel_id" in raid:
                try:
                    voice_channel = cog.bot.get_channel(raid["voice_channel_id"])
                    if voice_channel:
                        voice_mention = f"\n🔊 Canal de voz arquivado: {voice_channel.mention}"
                        await voice_channel.delete(reason="Raid concluída")
                except Exception as e:
                    print(f"Erro ao deletar canal de voz: {e}")

            # Executar limpeza final (deve incluir arquivamento da thread)
            await cog.handle_raid_completion(self.raid_id)

            # Feedback ao usuário
            await interaction.followup.send(
                f"✅ Raid concluída com sucesso!{voice_mention}",
                ephemeral=True
            )

        except Exception as e:
            print(f"Erro ao concluir raid: {e}")
            await interaction.followup.send(
                "❌ Falha ao processar conclusão da raid!",
                ephemeral=True
            )


def setup(bot: commands.Bot):
    bot.add_cog(RaidSystem(bot))