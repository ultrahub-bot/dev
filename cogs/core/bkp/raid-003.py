# enhanced_raid_builder.py - Sistema RAID Builder Completo com Integração de Canais de Voz
import discord
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup, Option
from discord.ui import Button, View, Select, Modal, InputText
from discord import ButtonStyle, Embed, Color
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import json
import logging
from database import db
from config import RAID_CHANNEL_ID

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes
REQUIRED_VOICE_CHANNEL_ID = 1406201396054986794

class RaidConfigModal(Modal):
    """Modal para configuração avançada de raid"""
    def __init__(self, boss: Dict, mode: str, cog):
        title_map = {
            'private': f"Raid Privada - {boss['name']}",
            'help': f"Pedir Ajuda - {boss['name']}"
        }
        super().__init__(title=title_map.get(mode, f"Configurar - {boss['name']}"))
        self.boss = boss
        self.mode = mode
        self.cog = cog
        
        if mode == 'private':
            self.add_item(InputText(
                label="Tamanho do grupo (opcional)",
                placeholder=f"Padrão: {boss['party_size']} jogadores",
                required=False,
                max_length=2
            ))
        
        self.add_item(InputText(
            label="Descrição da raid",
            placeholder="Ex: Precisando de help com esse boss...",
            required=False,
            max_length=500
        ))
        
        self.add_item(InputText(
            label="Horário preferido",
            placeholder="Ex: 20:00, agora, em 30min...",
            required=False,
            max_length=100
        ))
    
    async def callback(self, interaction: discord.Interaction):
        # Parse do tamanho do grupo
        party_size = self.boss['party_size']
        if self.mode == 'private' and self.children[0].value:
            try:
                custom_size = int(self.children[0].value.strip())
                if 1 <= custom_size <= self.boss['party_size']:
                    party_size = custom_size
            except ValueError:
                pass
        
        description_idx = 1 if self.mode == 'private' else 0
        schedule_idx = 2 if self.mode == 'private' else 1
        
        description = self.children[description_idx].value or "Nenhuma descrição fornecida"
        schedule = self.children[schedule_idx].value or "Agora"
        
        # Criar raid baseada no modo
        if self.mode == 'private':
            raid_data = await self.cog.create_raid(
                boss_id=self.boss['id'],
                leader_id=interaction.user.id,
                guild_id=interaction.guild.id,
                is_private=True,
                description=description,
                scheduled_time=schedule,
                custom_party_size=party_size
            )
        elif self.mode == 'help':
            raid_data = await self.cog.create_help_raid(
                boss_id=self.boss['id'],
                leader_id=interaction.user.id,
                guild_id=interaction.guild.id,
                description=description,
                scheduled_time=schedule
            )
        
        if raid_data:
            channel = self.cog.bot.get_channel(RAID_CHANNEL_ID)
            if channel:
                await self.cog.send_raid_embed(raid_data, channel)
            
            mode_text = {
                'private': "privada criada",
                'help': "de ajuda criada"
            }
            
            await interaction.response.send_message(
                f"✅ Raid {mode_text[self.mode]} para **{self.boss['name']}**!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Erro ao criar a raid. Tente novamente.",
                ephemeral=True
            )

class InviteModal(Modal):
    """Modal para convidar jogadores"""
    def __init__(self, raid_id: int, cog):
        super().__init__(title="Convidar Jogadores")
        self.raid_id = raid_id
        self.cog = cog
        
        self.add_item(InputText(
            label="Jogadores para convidar",
            placeholder="@usuario1 @usuario2 ou mencione diretamente",
            style=discord.InputTextStyle.paragraph,
            required=True,
            max_length=1000
        ))
    
    async def callback(self, interaction: discord.Interaction):
        mentions_text = self.children[0].value
        
        # Extrair menções de usuários
        mentioned_users = []
        if interaction.message and interaction.message.mentions:
            mentioned_users.extend(interaction.message.mentions)
        
        # Parse manual de menções no texto
        import re
        user_ids = re.findall(r'<@!?(\d+)>', mentions_text)
        for user_id in user_ids:
            try:
                user = await self.cog.bot.fetch_user(int(user_id))
                if user not in mentioned_users:
                    mentioned_users.append(user)
            except:
                continue
        
        if not mentioned_users:
            return await interaction.response.send_message(
                "❌ Nenhum usuário válido encontrado! Use @usuario ou mencione diretamente.",
                ephemeral=True
            )
        
        # Enviar convites
        sent_invites = []
        for user in mentioned_users:
            if user.id != interaction.user.id:  # Não convidar a si mesmo
                success = await self.cog.send_raid_invite(self.raid_id, user, interaction.user)
                if success:
                    sent_invites.append(user.mention)
        
        if sent_invites:
            await interaction.response.send_message(
                f"✅ Convites enviados para: {', '.join(sent_invites)}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Nenhum convite pôde ser enviado.",
                ephemeral=True
            )

class RaidBuilderSystem(commands.Cog):
    """Sistema completo de RAID Builder com integração de canais de voz"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Armazenamento em memória
        self.active_raids: Dict[int, Dict] = {}
        self.voice_queue_channels: Dict[int, int] = {}  # boss_id -> voice_channel_id
        self.voice_channel_raids: Dict[int, int] = {}  # voice_channel_id -> raid_id
        self.user_raids: Dict[int, Set[int]] = {}
        self.raid_messages: Dict[int, Dict] = {}
        self.pending_invites: Dict[int, Dict] = {}  # user_id -> {raid_id: invite_data}
        
        # Iniciar tarefas em background
        self.cleanup_task.start()
        self.voice_monitor.start()
        self.ready_check_monitor.start()
    
    def cog_unload(self):
        """Limpar tarefas ao descarregar cog"""
        self.cleanup_task.cancel()
        self.voice_monitor.cancel()
        self.ready_check_monitor.cancel()
    
    # ═══════════════════════════════════════════════════════════════════════════════════════
    # LISTENERS DE EVENTOS DE VOZ
    # ═══════════════════════════════════════════════════════════════════════════════════════
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Monitora entradas/saídas de canais de voz para gerenciar filas automáticas"""
        # Verificar se saiu de um canal de fila
        if before.channel and before.channel.id in self.voice_channel_raids:
            await self.handle_voice_leave(member, before.channel)
        
        # Verificar se entrou em um canal de fila
        if after.channel and after.channel.id in self.voice_channel_raids:
            await self.handle_voice_join(member, after.channel)
    
    async def handle_voice_join(self, member: discord.Member, voice_channel: discord.VoiceChannel):
        """Handler para quando alguém entra em um canal de fila de raid"""
        if member.bot:  # Ignorar bots
            return
        
        raid_id = self.voice_channel_raids.get(voice_channel.id)
        if not raid_id or raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        
        # Verificar se a raid ainda está recrutando
        if raid['status'] != 'recruiting':
            return
        
        # Verificar se já está na raid
        if member.id in raid['members']:
            return
        
        # Verificar se há vaga
        if len(raid['members']) >= raid['party_size']:
            # Notificar que está cheio
            try:
                await member.send(
                    f"❌ A fila para **{db.get_boss(raid['boss_id'])['name']}** está cheia! "
                    f"Você será movido para fora do canal."
                )
            except:
                pass
            
            # Mover para canal original se possível
            required_channel = self.bot.get_channel(REQUIRED_VOICE_CHANNEL_ID)
            if required_channel:
                try:
                    await member.move_to(required_channel)
                except:
                    pass
            return
        
        # Adicionar à raid
        await self.add_member_to_raid(raid_id, member.id)
        boss = db.get_boss(raid['boss_id'])
        
        # Notificar o usuário
        try:
            await member.send(
                f"✅ Você entrou na fila para **{boss['name']}**!\n"
                f"👥 Posição: {len(raid['members'])}/{raid['party_size']}\n"
                f"📋 Permaneça no canal de voz para manter sua posição."
            )
        except:
            pass
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)
        
        # Verificar se está completa
        if len(raid['members']) >= raid['party_size']:
            await self.handle_raid_filled(raid_id)
    
    async def handle_voice_leave(self, member: discord.Member, voice_channel: discord.VoiceChannel):
        """Handler para quando alguém sai de um canal de fila de raid - VERSÃO MELHORADA"""
        if member.bot:
            return
        
        raid_id = self.voice_channel_raids.get(voice_channel.id)
        if not raid_id or raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        
        # Se a raid está em progresso ou concluída, não remover do grupo
        if raid['status'] in ['in_progress', 'completed', 'failed']:
            return
        
        # Se o membro estava na raid, remover
        if member.id in raid['members']:
            await self.remove_member_from_raid(raid_id, member.id)
            
            # Notificar apenas se a raid ainda está recrutando
            if raid['status'] == 'recruiting':
                try:
                    boss = db.get_boss(raid['boss_id'])
                    await member.send(
                        f"📤 Você saiu da fila para **{boss['name']}** ao deixar o canal de voz."
                    )
                except:
                    pass
    
    async def handle_raid_filled(self, raid_id: int):
        """Versão simplificada para quando uma raid fica cheia"""
        if raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        boss = db.get_boss(raid['boss_id'])
        
        # Notificar no canal principal
        channel = self.bot.get_channel(RAID_CHANNEL_ID)
        if channel:
            mentions = []
            for user_id in raid['members']:
                user = self.bot.get_user(user_id)
                if user:
                    mentions.append(user.mention)
            
            if mentions:
                await channel.send(
                    f"🎉 **Fila completa para {boss['name']}!**\n"
                    f"{' '.join(mentions)}\n"
                    f"⏰ Ready check automático iniciando em 10 segundos!"
                )
        
        # Para raids públicas e voice queue, iniciar ready check automático
        if raid.get('auto_ready_check', False):
            await asyncio.sleep(10)
            if raid_id in self.active_raids and raid['status'] == 'recruiting':
                await self.start_auto_ready_check(raid_id)
    
    async def start_auto_ready_check(self, raid_id: int):
        """Ready check automático com timeout menor"""
        if raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        
        # Iniciar ready check
        raid['ready_check_started'] = True
        raid['ready_check_expires'] = datetime.utcnow() + timedelta(minutes=1)  # Apenas 1 minuto
        raid['confirmed_members'].clear()
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)
        
        # Notificar no canal de voz e texto
        boss = db.get_boss(raid['boss_id'])
        text_channel = self.bot.get_channel(RAID_CHANNEL_ID)
        
        mentions = []
        for user_id in raid['members']:
            user = self.bot.get_user(user_id)
            if user:
                mentions.append(user.mention)
        
        ready_message = (
            f"🎯 **READY CHECK AUTOMÁTICO!**\n"
            f"🎮 Boss: **{boss['name']}**\n"
            f"⏰ Vocês têm 1 minuto para confirmar presença!\n"
            f"📋 Cliquem em **✅ Confirmar** na mensagem da raid."
        )
        
        if text_channel and mentions:
            await text_channel.send(f"{ready_message}\n{' '.join(mentions)}")
    
    # ═══════════════════════════════════════════════════════════════════════════════════════
    # COMANDO PRINCIPAL - RAID BUILDER
    # ═══════════════════════════════════════════════════════════════════════════════════════
    
    raid_group = SlashCommandGroup("raid", "Sistema de raids e matchmaking")
    
    @raid_group.command(name="builder", description="🏰 Abre o Raid Builder")

    async def raid_builder(self, ctx: discord.ApplicationContext):
        """Interface principal do Raid Builder - VERSÃO ATUALIZADA"""
        await ctx.defer(ephemeral=True)
        
        # Verificar se o usuário está no canal de voz necessário
        if not ctx.author.voice or ctx.author.voice.channel.id != REQUIRED_VOICE_CHANNEL_ID:
            required_channel = self.bot.get_channel(REQUIRED_VOICE_CHANNEL_ID)
            channel_mention = required_channel.mention if required_channel else f"<#{REQUIRED_VOICE_CHANNEL_ID}>"
            
            return await ctx.followup.send(
                f"❌ **Você precisa estar no canal de voz {channel_mention} para usar o Raid Builder!**\n"
                f"🎤 Entre no canal e tente novamente.",
                ephemeral=True
            )
        
        # Criar embed inicial
        embed = Embed(
            title="🏰 RAID BUILDER",
            description="Escolha como você quer formar sua raid:",
            color=Color.blue()
        )
        
        embed.add_field(
            name="🌐 **PÚBLICO**",
            value="Crie uma raid aberta para todos\n"
                "• Qualquer um pode entrar\n"
                "• Ready check automático\n"
                "• Rápido e simples",
            inline=False
        )
        
        embed.add_field(
            name="🎤 **FILA DE VOZ**",
            value="Crie uma fila por canal de voz\n"
                "• Canal específico para cada boss\n"
                "• Entre no canal = entre na fila\n"
                "• Automático e intuitivo",
            inline=False
        )
        
        embed.add_field(
            name="🔒 **PRIVADO**",
            value="Crie uma raid personalizada\n"
                "• Convide jogadores específicos\n"
                "• Controle total sobre participantes\n"
                "• Tamanho de grupo customizável",
            inline=False
        )
        
        embed.set_footer(text="Selecione uma opção abaixo para continuar")
        
        # Criar view com botões
        view = View(timeout=60)
        
        public_btn = Button(
            label="🌐 Público",
            style=ButtonStyle.green,
            custom_id="raid_mode_public"
        )
        voice_queue_btn = Button(
            label="🎤 Fila de Voz",
            style=ButtonStyle.blurple,
            custom_id="raid_mode_voice_queue"
        )
        private_btn = Button(
            label="🔒 Privado",
            style=ButtonStyle.gray,
            custom_id="raid_mode_private"
        )
        
        async def mode_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message(
                    "❌ Apenas quem abriu pode selecionar!",
                    ephemeral=True
                )
            
            mode = interaction.data["custom_id"].replace("raid_mode_", "")
            await self.show_boss_selection(interaction, mode)
        
        public_btn.callback = mode_callback
        voice_queue_btn.callback = mode_callback
        private_btn.callback = mode_callback
        
        view.add_item(public_btn)
        view.add_item(voice_queue_btn)
        view.add_item(private_btn)
        
        await ctx.followup.send(embed=embed, view=view, ephemeral=True)

    async def show_boss_selection(self, interaction: discord.Interaction, mode: str):
        """Versão corrigida da seleção de bosses"""
        try:
            bosses = db.list_bosses()
        except Exception as e:
            logger.error(f"Error fetching bosses: {e}")
            return await interaction.response.send_message(
                "Erro ao buscar bosses no banco de dados!",
                ephemeral=True
            )
        
        if not bosses:
            return await interaction.response.send_message(
                "Nenhum boss disponível!",
                ephemeral=True
            )
        
        # Filtrar bosses visíveis
        visible_bosses = [b for b in bosses if not b.get('is_hidden', False)]
        
        if not visible_bosses:
            return await interaction.response.send_message(
                "Nenhum boss público disponível!",
                ephemeral=True
            )
        
        # Criar embed de seleção
        mode_titles = {
            'voice_queue': 'Fila de Voz',
            'private': 'Raid Privada',
            'public': 'Raid Pública'  # Novo modo
        }
        
        embed = Embed(
            title=f"🎯 {mode_titles[mode]}",
            description="Selecione o boss que você quer enfrentar:",
            color=Color.gold()
        )
        
        # Mostrar estatísticas das filas ativas (apenas no modo voice_queue)
        if mode == 'voice_queue':
            active_queues = []
            for boss_id, voice_channel_id in self.voice_queue_channels.items():
                voice_channel = self.bot.get_channel(voice_channel_id)
                if voice_channel:
                    boss = db.get_boss(boss_id)
                    member_count = len([m for m in voice_channel.members if not m.bot])
                    if member_count > 0:
                        active_queues.append(f"**{boss['name']}:** {member_count}/{boss['party_size']} no canal")
            
            if active_queues:
                embed.add_field(
                    name="🎤 Canais Ativos",
                    value="\n".join(active_queues[:5]),
                    inline=False
                )
        
        # Criar select menu
        view = View(timeout=60)
        
        boss_options = []
        for boss in visible_bosses[:25]:  # Limite do Discord
            # Adicionar info do canal no modo voice_queue
            queue_text = ""
            if mode == 'voice_queue' and boss['id'] in self.voice_queue_channels:
                voice_channel_id = self.voice_queue_channels[boss['id']]
                voice_channel = self.bot.get_channel(voice_channel_id)
                if voice_channel:
                    member_count = len([m for m in voice_channel.members if not m.bot])
                    if member_count > 0:
                        queue_text = f" [{member_count}/{boss['party_size']} no canal]"
            
            boss_options.append(discord.SelectOption(
                label=f"{boss['name']} ({boss['party_size']}p){queue_text}",
                description=f"Lvl {boss['level']} - {boss['map']} - Dif: {boss['difficulty']}/5",
                value=str(boss['id'])  # CORREÇÃO: apenas o ID do boss
            ))
        
        select = Select(
            placeholder="Escolha um boss...",
            options=boss_options
        )
        
        async def boss_select_callback(select_interaction: discord.Interaction):
            if select_interaction.user.id != interaction.user.id:
                return await select_interaction.response.send_message(
                    "Apenas quem abriu pode selecionar!",
                    ephemeral=True
                )
            
            # CORREÇÃO: parsing simplificado
            boss_id = int(select.values[0])
            boss = db.get_boss(boss_id)
            
            # Direcionar para o handler apropriado
            if mode == 'voice_queue':
                await self.handle_voice_queue_creation(select_interaction, boss)
            elif mode == 'private':
                await self.handle_private_raid(select_interaction, boss)
            elif mode == 'public':
                await self.handle_public_raid(select_interaction, boss)
        
        select.callback = boss_select_callback
        view.add_item(select)
        
        await interaction.response.edit_message(embed=embed, view=view)

    @raid_group.command(name="public", description="🌐 Cria uma raid pública rapidamente")
    async def create_public_raid(
        self,
        ctx: discord.ApplicationContext,
        boss_name: Option(str, "Nome ou parte do nome do boss", required=True),
        description: Option(str, "Descrição da raid", required=False, default="")
    ):
        """Comando direto para criar raid pública"""
        await ctx.defer()
        
        # Buscar boss pelo nome
        try:
            bosses = db.list_bosses()
            matching_bosses = [
                b for b in bosses 
                if boss_name.lower() in b['name'].lower() and not b.get('is_hidden', False)
            ]
            
            if not matching_bosses:
                return await ctx.followup.send(
                    f"❌ Boss '{boss_name}' não encontrado!\n"
                    f"Use `/raid builder` para ver todos os bosses disponíveis."
                )
            
            # Se múltiplos matches, pegar o primeiro
            boss = matching_bosses[0]
            
            # Verificar se já existe raid ativa para este boss pelo mesmo usuário
            user_raids = self.user_raids.get(ctx.author.id, set())
            for raid_id in user_raids:
                if raid_id in self.active_raids:
                    existing_raid = self.active_raids[raid_id]
                    if existing_raid['boss_id'] == boss['id'] and existing_raid['status'] == 'recruiting':
                        return await ctx.followup.send(
                            f"❌ Você já tem uma raid ativa para **{boss['name']}**!\n"
                            f"Cancele a raid existente primeiro se quiser criar outra."
                        )
            
            # Criar raid pública
            raid_data = await self.create_raid(
                boss_id=boss['id'],
                leader_id=ctx.author.id,
                guild_id=ctx.guild.id,
                is_private=False,
                description=description or f"Raid pública para {boss['name']} - Todos bem-vindos!",
                scheduled_time="Agora",
                is_public=True
            )
            
            if not raid_data:
                return await ctx.followup.send(
                    "❌ Erro ao criar a raid. Tente novamente."
                )
            
            # Enviar embed da raid
            channel = self.bot.get_channel(RAID_CHANNEL_ID)
            if channel:
                await self.send_raid_embed(raid_data, channel)
            
            await ctx.followup.send(
                f"✅ **Raid pública criada para {boss['name']}!**\n"
                f"👥 Capacidade: {boss['party_size']} jogadores\n"
                f"📋 A raid foi postada no canal de raids - qualquer um pode entrar!\n"
                f"🚀 Quando a raid estiver cheia, o ready check começará automaticamente."
            )
            
        except Exception as e:
            logger.error(f"Error in create_public_raid: {e}")
            await ctx.followup.send("❌ Erro interno. Tente novamente.")
    
    # ═══════════════════════════════════════════════════════════════════════════════════════
    # HANDLERS PARA DIFERENTES MODOS
    # ═══════════════════════════════════════════════════════════════════════════════════════

    async def cleanup_raid(self, raid_id: int):
        """Limpa completamente uma raid da memória"""
        if raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        
        # Remover de índices de usuários
        for user_id in raid['members']:
            if user_id in self.user_raids:
                self.user_raids[user_id].discard(raid_id)
                if not self.user_raids[user_id]:
                    del self.user_raids[user_id]
        
        # Remover referências de mensagens
        if raid_id in self.raid_messages:
            del self.raid_messages[raid_id]
        
        # Remover da lista ativa
        del self.active_raids[raid_id]
        
        logger.info(f"Raid {raid_id} cleaned up from memory")

    async def handle_voice_queue_creation(self, interaction: discord.Interaction, boss: Dict):
        """Handler para modo fila de voz - criar canal e raid"""
        boss_id = boss['id']
        
        # Verificar se já existe uma fila/raid ativa para este boss
        if boss_id in self.voice_queue_channels:
            voice_channel = self.bot.get_channel(self.voice_queue_channels[boss_id])
            if voice_channel:
                return await interaction.response.send_message(
                    f"⚠ Já existe uma fila ativa para **{boss['name']}**!\n"
                    f"🎤 Entre no canal {voice_channel.mention} para participar.",
                    ephemeral=True
                )
        
        # Criar raid
        raid_data = await self.create_raid(
            boss_id=boss_id,
            leader_id=interaction.user.id,
            guild_id=interaction.guild.id,
            is_private=False,
            description=f"Fila de voz para {boss['name']} - Entre no canal para participar!",
            scheduled_time="Agora",
            is_voice_queue=True
        )
        
        if not raid_data:
            return await interaction.response.send_message(
                "⚠ Erro ao criar a raid. Tente novamente.",
                ephemeral=True
            )
        
        # Criar canal de voz para a fila
        voice_channel = await self.create_queue_voice_channel(boss, raid_data['id'])
        
        if not voice_channel:
            # Cancelar raid se não conseguiu criar canal
            await self.cleanup_raid(raid_data['id'])
            return await interaction.response.send_message(
                "⚠ Erro ao criar canal de voz. Tente novamente.",
                ephemeral=True
            )
        
        # Associar canal à raid
        self.voice_queue_channels[boss_id] = voice_channel.id
        self.voice_channel_raids[voice_channel.id] = raid_data['id']
        
        # Enviar embed da raid
        channel = self.bot.get_channel(RAID_CHANNEL_ID)
        if channel:
            await self.send_raid_embed(raid_data, channel)
        
        # Mover o líder para o canal criado
        try:
            await interaction.user.move_to(voice_channel)
        except:
            pass
        
        await interaction.response.send_message(
            f"✅ **Fila de voz criada para {boss['name']}!**\n"
            f"🎤 Canal: {voice_channel.mention}\n"
            f"👥 Capacidade: {boss['party_size']} jogadores\n"
            f"📋 Qualquer pessoa que entrar no canal será adicionada automaticamente à fila!",
            ephemeral=True
        )
        
    async def handle_public_raid(self, interaction: discord.Interaction, boss: Dict):
        """Handler para modo público - criação simples e direta"""
        # Criar raid pública imediatamente
        raid_data = await self.create_raid(
            boss_id=boss['id'],
            leader_id=interaction.user.id,
            guild_id=interaction.guild.id,
            is_private=False,
            description=f"Raid pública para {boss['name']} - Qualquer um pode entrar!",
            scheduled_time="Agora",
            is_public=True
        )
        
        if not raid_data:
            return await interaction.response.send_message(
                "Erro ao criar a raid. Tente novamente.",
                ephemeral=True
            )
        
        # Enviar embed da raid
        channel = self.bot.get_channel(RAID_CHANNEL_ID)
        if channel:
            await self.send_raid_embed(raid_data, channel)
        
        await interaction.response.send_message(
            f"✅ **Raid pública criada para {boss['name']}!**\n"
            f"👥 Capacidade: {boss['party_size']} jogadores\n"
            f"📋 Qualquer pessoa pode entrar usando o botão 🎮 Entrar!\n"
            f"🔔 A raid será postada no canal de raids.",
            ephemeral=True
        )

    async def handle_private_raid(self, interaction: discord.Interaction, boss: Dict):
        """Handler para modo privado - abrir modal de configuração"""
        modal = RaidConfigModal(boss, 'private', self)
        await interaction.response.send_modal(modal)

    async def create_queue_voice_channel(self, boss: Dict, raid_id: int) -> Optional[discord.VoiceChannel]:
        """Cria canal de voz para fila do boss"""
        try:
            guild = self.bot.guilds[0]  # Assumindo primeiro guild
            
            # Criar canal de voz
            voice_channel = await guild.create_voice_channel(
                name=f"🎯 Fila: {boss['name']}",
                user_limit=boss['party_size'],
                reason=f"Fila automática para {boss['name']} - Raid {raid_id}"
            )
            
            logger.info(f"Queue voice channel created: {voice_channel.id} for boss {boss['id']}")
            return voice_channel
            
        except Exception as e:
            logger.error(f"Error creating queue voice channel: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════════════════════
    # CRIAÇÃO E GERENCIAMENTO DE RAIDS
    # ═══════════════════════════════════════════════════════════════════════════════════════
    
    async def create_raid(
        self,
        boss_id: int,
        leader_id: int,
        guild_id: int,
        is_private: bool = False,
        description: str = "",
        scheduled_time: str = "Agora",
        custom_party_size: int = None,
        requested_help: bool = False,
        is_voice_queue: bool = False,
        is_public: bool = False
    ) -> Optional[Dict]:
        """Versão corrigida da criação de raid"""
        try:
            boss = db.get_boss(boss_id)
            if not boss:
                logger.error(f"Boss {boss_id} not found")
                return None
            
            # Gerar ID único
            raid_id = max(self.active_raids.keys(), default=0) + 1
            
            raid_data = {
                'id': raid_id,
                'boss_id': boss_id,
                'leader_id': leader_id,
                'guild_id': guild_id,
                'members': [leader_id],  # Líder já entra automaticamente
                'confirmed_members': set(),
                'status': 'recruiting',
                'is_private': is_private,
                'is_public': is_public,
                'requested_help': requested_help,
                'is_voice_queue': is_voice_queue,
                'description': description,
                'scheduled_time': scheduled_time,
                'party_size': custom_party_size or boss['party_size'],
                'created_at': datetime.utcnow(),
                'started_at': None,
                'completed_at': None,
                'ready_check_started': False,
                'ready_check_expires': None,
                'auto_ready_check': is_public or is_voice_queue  # Auto ready check para raids públicas
            }
            
            self.active_raids[raid_id] = raid_data
            
            # Atualizar índice de usuário
            if leader_id not in self.user_raids:
                self.user_raids[leader_id] = set()
            self.user_raids[leader_id].add(raid_id)
            
            logger.info(f"Raid {raid_id} created - Boss: {boss['name']}, Leader: {leader_id}, Type: {'Public' if is_public else 'Private' if is_private else 'Voice Queue' if is_voice_queue else 'Help'}")
            
            return raid_data
            
        except Exception as e:
            logger.error(f"Error creating raid: {e}")
            return None
    
    async def add_member_to_raid(self, raid_id: int, user_id: int):
        """Adiciona um membro à raid"""
        if raid_id not in self.active_raids:
            return False
        
        raid = self.active_raids[raid_id]
        
        # Verificar se há vaga
        if len(raid['members']) >= raid['party_size']:
            return False
        
        if user_id not in raid['members']:
            raid['members'].append(user_id)
            
            # Atualizar índice de usuário
            if user_id not in self.user_raids:
                self.user_raids[user_id] = set()
            self.user_raids[user_id].add(raid_id)
            
            logger.info(f"User {user_id} added to raid {raid_id}")
        
        return True
    
    async def remove_member_from_raid(self, raid_id: int, user_id: int):
        """Remove um membro da raid"""
        if raid_id not in self.active_raids:
            return False
        
        raid = self.active_raids[raid_id]
        
        if user_id in raid['members']:
            raid['members'].remove(user_id)
            raid['confirmed_members'].discard(user_id)
            
            # Atualizar índice de usuário
            if user_id in self.user_raids:
                self.user_raids[user_id].discard(raid_id)
                if not self.user_raids[user_id]:
                    del self.user_raids[user_id]
            
            # Se o líder saiu
            if user_id == raid['leader_id']:
                if raid['members']:
                    # Promover novo líder
                    raid['leader_id'] = raid['members'][0]
                    logger.info(f"New leader {raid['members'][0]} for raid {raid_id}")
                else:
                    # Cancelar raid se não há mais membros
                    await self.cancel_raid(raid_id)
                    return True
            
            logger.info(f"User {user_id} removed from raid {raid_id}")
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)
        return True
    
    # ═══════════════════════════════════════════════════════════════════════════════════════
    # SISTEMA DE CONVITES
    # ═══════════════════════════════════════════════════════════════════════════════════════
    
    async def send_raid_invite(self, raid_id: int, target_user: discord.User, inviter: discord.User) -> bool:
        """Envia convite de raid para um usuário"""
        if raid_id not in self.active_raids:
            return False
        
        raid = self.active_raids[raid_id]
        boss = db.get_boss(raid['boss_id'])
        
        # Verificar se a raid ainda aceita membros
        if len(raid['members']) >= raid['party_size']:
            return False
        
        # Verificar se o usuário já está na raid
        if target_user.id in raid['members']:
            return False
        
        # Criar embed do convite
        embed = Embed(
            title="📩 Convite para Raid",
            description=f"**{inviter.display_name}** te convidou para uma raid!",
            color=Color.blue()
        )
        
        embed.add_field(
            name="🎯 Boss",
            value=f"**{boss['name']}**\nLevel {boss['level']} - {boss['map']}",
            inline=True
        )
        
        embed.add_field(
            name="👥 Participantes",
            value=f"{len(raid['members'])}/{raid['party_size']}",
            inline=True
        )
        
        embed.add_field(
            name="📋 Descrição",
            value=raid['description'] or "Sem descrição",
            inline=False
        )
        
        # Criar view com botões de aceitar/recusar
        view = View(timeout=300)  # 5 minutos para responder
        
        accept_btn = Button(
            label="✅ Aceitar",
            style=ButtonStyle.green,
            custom_id=f"invite_accept_{raid_id}"
        )
        decline_btn = Button(
            label="❌ Recusar",
            style=ButtonStyle.red,
            custom_id=f"invite_decline_{raid_id}"
        )
        
        async def invite_callback(interaction: discord.Interaction):
            if interaction.user.id != target_user.id:
                return await interaction.response.send_message(
                    "❌ Este convite não é para você!",
                    ephemeral=True
                )
            
            action = interaction.data["custom_id"].split("_")[1]
            
            if action == "accept":
                # Verificar se ainda há vaga
                current_raid = self.active_raids.get(raid_id)
                if not current_raid:
                    return await interaction.response.send_message(
                        "❌ Esta raid não existe mais!",
                        ephemeral=True
                    )
                
                if len(current_raid['members']) >= current_raid['party_size']:
                    return await interaction.response.send_message(
                        "❌ Esta raid já está cheia!",
                        ephemeral=True
                    )
                
                # Adicionar à raid
                await self.add_member_to_raid(raid_id, target_user.id)
                
                await interaction.response.send_message(
                    f"✅ Você entrou na raid **{boss['name']}**!",
                    ephemeral=True
                )
                
                # Atualizar embed da raid
                await self.update_raid_embed(raid_id)
                
            else:  # decline
                await interaction.response.send_message(
                    "❌ Convite recusado.",
                    ephemeral=True
                )
            
            # Remover convite pendente
            if target_user.id in self.pending_invites:
                self.pending_invites[target_user.id].pop(raid_id, None)
                if not self.pending_invites[target_user.id]:
                    del self.pending_invites[target_user.id]
            
            # Desabilitar botões
            for item in view.children:
                item.disabled = True
            await interaction.edit_original_response(view=view)
        
        accept_btn.callback = invite_callback
        decline_btn.callback = invite_callback
        
        view.add_item(accept_btn)
        view.add_item(decline_btn)
        
        try:
            # Enviar DM
            dm_message = await target_user.send(embed=embed, view=view)
            
            # Salvar convite pendente
            if target_user.id not in self.pending_invites:
                self.pending_invites[target_user.id] = {}
            
            self.pending_invites[target_user.id][raid_id] = {
                'inviter_id': inviter.id,
                'message_id': dm_message.id,
                'expires_at': datetime.utcnow() + timedelta(minutes=5)
            }
            
            return True
            
        except discord.Forbidden:
            # Usuário tem DMs fechadas
            logger.warning(f"Could not send DM invite to user {target_user.id}")
            return False
        except Exception as e:
            logger.error(f"Error sending raid invite: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════════════════════
    # SISTEMA DE EMBEDS E INTERFACE
    # ═══════════════════════════════════════════════════════════════════════════════════════
    
    async def send_raid_embed(self, raid_data: Dict, channel):
        """Envia o embed da raid"""
        try:
            embed = await self.create_raid_embed(raid_data)
            view = await self.create_raid_view(raid_data['id'])
            
            message = await channel.send(embed=embed, view=view)
            
            # Salvar referência da mensagem
            self.raid_messages[raid_data['id']] = {
                'channel_id': channel.id,
                'message_id': message.id
            }
            
            return message
            
        except Exception as e:
            logger.error(f"Error sending raid embed: {e}")
            return None
    
    async def create_raid_embed(self, raid_data: Dict) -> Embed:
        """Cria embed para uma raid"""
        boss = db.get_boss(raid_data['boss_id'])
        leader = self.bot.get_user(raid_data['leader_id'])
        
        # Cor baseada no status
        color_map = {
            'recruiting': Color.blue(),
            'ready_check': Color.gold(),
            'in_progress': Color.green(),
            'completed': Color.dark_grey(),
            'cancelled': Color.red()
        }
        
        embed = Embed(
            title=f"🎯 {boss['name']}",
            description=raid_data['description'],
            color=color_map.get(raid_data['status'], Color.blue())
        )
        
        # Informações básicas
        embed.add_field(
            name="👑 Líder",
            value=leader.mention if leader else f"<@{raid_data['leader_id']}>",
            inline=True
        )
        
        embed.add_field(
            name="📊 Status",
            value=raid_data['status'].upper(),
            inline=True
        )
        
        embed.add_field(
            name="👥 Participantes",
            value=f"{len(raid_data['members'])}/{raid_data['party_size']}",
            inline=True
        )
        
        # Lista de membros
        members_text = []
        for user_id in raid_data['members']:
            user = self.bot.get_user(user_id)
            status = "✅" if user_id in raid_data['confirmed_members'] else "❌"
            members_text.append(f"{status} {user.mention if user else f'<@{user_id}>'}")
        
        embed.add_field(
            name="🎮 Jogadores",
            value="\n".join(members_text) if members_text else "Nenhum participante",
            inline=False
        )
        
        # Informações adicionais
        if raid_data['ready_check_started'] and raid_data['ready_check_expires']:
            time_left = raid_data['ready_check_expires'] - datetime.utcnow()
            if time_left.total_seconds() > 0:
                embed.add_field(
                    name="⏰ Ready Check",
                    value=f"Expira em {int(time_left.total_seconds() // 60)}:{int(time_left.total_seconds() % 60):02d}",
                    inline=True
                )
        
        if raid_data['scheduled_time']:
            embed.add_field(
                name="🕒 Horário",
                value=raid_data['scheduled_time'],
                inline=True
            )
        
        # Footer com ID da raid
        embed.set_footer(text=f"Raid ID: {raid_data['id']} • Criada em {raid_data['created_at'].strftime('%H:%M')}")
        
        return embed
    
    async def create_raid_view(self, raid_id: int) -> View:
        """Cria view com botões para uma raid - VERSÃO MELHORADA"""
        if raid_id not in self.active_raids:
            return View()
        
        raid = self.active_raids[raid_id]
        view = View(timeout=None)
        
        # Botão de entrar (apenas se recrutando e não é voice queue)
        if raid['status'] == 'recruiting' and not raid['is_voice_queue']:
            join_btn = Button(
                label="🎮 Entrar",
                style=ButtonStyle.green,
                custom_id=f"raid_join_{raid_id}"
            )
            
            async def join_callback(interaction: discord.Interaction):
                if raid_id not in self.active_raids:
                    return await interaction.response.send_message(
                        "❌ Esta raid não existe mais!",
                        ephemeral=True
                    )
                
                current_raid = self.active_raids[raid_id]
                
                if len(current_raid['members']) >= current_raid['party_size']:
                    return await interaction.response.send_message(
                        "❌ Esta raid já está cheia!",
                        ephemeral=True
                    )
                
                if interaction.user.id in current_raid['members']:
                    return await interaction.response.send_message(
                        "❌ Você já está nesta raid!",
                        ephemeral=True
                    )
                
                await self.add_member_to_raid(raid_id, interaction.user.id)
                await interaction.response.send_message(
                    f"✅ Você entrou na raid **{db.get_boss(current_raid['boss_id'])['name']}**!",
                    ephemeral=True
                )
                
                await self.update_raid_embed(raid_id)
            
            join_btn.callback = join_callback
            view.add_item(join_btn)
        
        # Botão de sair (se está na raid)
        if raid['status'] == 'recruiting':
            leave_btn = Button(
                label="🚪 Sair",
                style=ButtonStyle.red,
                custom_id=f"raid_leave_{raid_id}"
            )
            
            async def leave_callback(interaction: discord.Interaction):
                if raid_id not in self.active_raids:
                    return await interaction.response.send_message(
                        "❌ Esta raid não existe mais!",
                        ephemeral=True
                    )
                
                current_raid = self.active_raids[raid_id]
                
                if interaction.user.id not in current_raid['members']:
                    return await interaction.response.send_message(
                        "❌ Você não está nesta raid!",
                        ephemeral=True
                    )
                
                await self.remove_member_from_raid(raid_id, interaction.user.id)
                await interaction.response.send_message(
                    f"✅ Você saiu da raid **{db.get_boss(current_raid['boss_id'])['name']}**!",
                    ephemeral=True
                )
            
            leave_btn.callback = leave_callback
            view.add_item(leave_btn)
        
        # Botão de ready check (apenas para líder)
        if raid['status'] == 'recruiting' and len(raid['members']) >= 2:
            ready_btn = Button(
                label="✅ Ready Check",
                style=ButtonStyle.blurple,
                custom_id=f"raid_ready_{raid_id}"
            )
            
            async def ready_callback(interaction: discord.Interaction):
                if raid_id not in self.active_raids:
                    return await interaction.response.send_message(
                        "❌ Esta raid não existe mais!",
                        ephemeral=True
                    )
                
                current_raid = self.active_raids[raid_id]
                
                if interaction.user.id != current_raid['leader_id']:
                    return await interaction.response.send_message(
                        "❌ Apenas o líder pode iniciar ready check!",
                        ephemeral=True
                    )
                
                await self.start_ready_check(raid_id, interaction)
            
            ready_btn.callback = ready_callback
            view.add_item(ready_btn)
        
        # Botão de confirmar (durante ready check)
        if raid['status'] == 'recruiting' and raid['ready_check_started']:
            confirm_btn = Button(
                label="✅ Confirmar",
                style=ButtonStyle.green,
                custom_id=f"raid_confirm_{raid_id}"
            )
            
            async def confirm_callback(interaction: discord.Interaction):
                if raid_id not in self.active_raids:
                    return await interaction.response.send_message(
                        "❌ Esta raid não existe mais!",
                        ephemeral=True
                    )
                
                current_raid = self.active_raids[raid_id]
                
                if interaction.user.id not in current_raid['members']:
                    return await interaction.response.send_message(
                        "❌ Você não está nesta raid!",
                        ephemeral=True
                    )
                
                if not current_raid['ready_check_started']:
                    return await interaction.response.send_message(
                        "❌ Não há ready check ativo!",
                        ephemeral=True
                    )
                
                current_raid['confirmed_members'].add(interaction.user.id)
                await interaction.response.send_message(
                    "✅ Presença confirmada!",
                    ephemeral=True
                )
                
                await self.update_raid_embed(raid_id)
                
                # Verificar se todos confirmaram
                if len(current_raid['confirmed_members']) == len(current_raid['members']):
                    await self.start_raid(raid_id)
            
            confirm_btn.callback = confirm_callback
            view.add_item(confirm_btn)


        if raid['status'] == 'in_progress' and len(raid['members']) > 0:
            complete_btn = Button(
                label="✅ Concluir",
                style=ButtonStyle.green,
                custom_id=f"raid_complete_{raid_id}",
                row=1
            )
            
            async def complete_callback(interaction: discord.Interaction):
                await self.complete_raid(raid_id, True, interaction)
            
            complete_btn.callback = complete_callback
            view.add_item(complete_btn)
            
            # Botão de falha
            fail_btn = Button(
                label="❌ Falhou",
                style=ButtonStyle.red,
                custom_id=f"raid_fail_{raid_id}",
                row=1
            )
            
            async def fail_callback(interaction: discord.Interaction):
                await self.complete_raid(raid_id, False, interaction)
            
            fail_btn.callback = fail_callback
            view.add_item(fail_btn)

        
        # Botão de convidar (apenas para líder)
        if raid['status'] == 'recruiting':
            invite_btn = Button(
                label="📩 Convidar",
                style=ButtonStyle.gray,
                custom_id=f"raid_invite_{raid_id}"
            )
            
            async def invite_callback(interaction: discord.Interaction):
                if raid_id not in self.active_raids:
                    return await interaction.response.send_message(
                        "❌ Esta raid não existe mais!",
                        ephemeral=True
                    )
                
                current_raid = self.active_raids[raid_id]
                
                if interaction.user.id != current_raid['leader_id']:
                    return await interaction.response.send_message(
                        "❌ Apenas o líder pode convidar jogadores!",
                        ephemeral=True
                    )

                
                modal = InviteModal(raid_id, self)
                await interaction.response.send_modal(modal)
            
            invite_btn.callback = invite_callback
            view.add_item(invite_btn)


        
        return view
    
    async def update_raid_embed(self, raid_id: int):
        """Atualiza o embed da raid"""
        if raid_id not in self.active_raids or raid_id not in self.raid_messages:
            return
        
        raid = self.active_raids[raid_id]
        message_info = self.raid_messages[raid_id]
        
        try:
            channel = self.bot.get_channel(message_info['channel_id'])
            if not channel:
                return
            
            message = await channel.fetch_message(message_info['message_id'])
            if not message:
                return
            
            embed = await self.create_raid_embed(raid)
            view = await self.create_raid_view(raid_id)
            
            await message.edit(embed=embed, view=view)
            
        except discord.NotFound:
            # Mensagem foi deletada
            del self.raid_messages[raid_id]
        except Exception as e:
            logger.error(f"Error updating raid embed {raid_id}: {e}")
    

    # ═══════════════════════════════════════════════════════════════════════════════════════
    # GERENCIAMENTO DE READY CHECK E INÍCIO DE RAID
    # ═══════════════════════════════════════════════════════════════════════════════════════
    async def start_raid(self, raid_id: int):
        """Inicia uma raid de forma simplificada"""
        if raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        raid['status'] = 'in_progress'
        raid['started_at'] = datetime.utcnow()
        raid['ready_check_started'] = False
        
        boss = db.get_boss(raid['boss_id'])
        
        # Notificar todos os membros
        channel = self.bot.get_channel(RAID_CHANNEL_ID)
        mentions = []
        
        for user_id in raid['members']:
            user = self.bot.get_user(user_id)
            if user:
                mentions.append(user.mention)
                try:
                    await user.send(
                        f"🚀 **RAID INICIADA!**\n"
                        f"A raid para **{boss['name']}** começou!\n"
                        f"🎮 Boa sorte e bom farming!"
                    )
                except:
                    pass
        
        # Notificar no canal principal
        if channel and mentions:
            await channel.send(
                f"🚀 **RAID INICIADA!**\n"
                f"**{boss['name']}** - {' '.join(mentions)}\n"
                f"🎮 Boa sorte pessoal! Lembrem-se de marcar como concluída quando terminarem."
            )
        
        await self.update_raid_embed(raid_id)
        logger.info(f"Raid {raid_id} started for boss {boss['name']}")

    async def cancel_raid(self, raid_id: int, reason: str = "Raid cancelada"):
        """Cancela uma raid e limpa todos os recursos associados"""
        if raid_id not in self.active_raids:
            return False
        
        raid = self.active_raids[raid_id]
        boss = db.get_boss(raid['boss_id'])
        
        # Marcar como cancelada
        raid['status'] = 'cancelled'
        raid['completed_at'] = datetime.utcnow()
        
        # Mover jogadores de volta para o canal original se estiverem em canal da raid
        required_channel = self.bot.get_channel(REQUIRED_VOICE_CHANNEL_ID)
        
        # Se é uma raid de voice queue, tratar o canal de voz
        if raid.get('is_voice_queue') and raid['boss_id'] in self.voice_queue_channels:
            voice_channel_id = self.voice_queue_channels[raid['boss_id']]
            voice_channel = self.bot.get_channel(voice_channel_id)
            
            if voice_channel and required_channel:
                # Mover todos os membros de volta
                for member in voice_channel.members:
                    if not member.bot:
                        try:
                            await member.move_to(required_channel)
                        except:
                            pass
                
                # Deletar canal após mover todos
                try:
                    await voice_channel.delete(reason=f"Raid {raid_id} cancelled")
                except:
                    pass
            
            # Limpar associações
            if raid['boss_id'] in self.voice_queue_channels:
                del self.voice_queue_channels[raid['boss_id']]
            if voice_channel_id in self.voice_channel_raids:
                del self.voice_channel_raids[voice_channel_id]
        
        # Notificar todos os membros
        for user_id in raid['members']:
            user = self.bot.get_user(user_id)
            if user:
                try:
                    await user.send(
                        f"❌ **Raid Cancelada!**\n"
                        f"A raid para **{boss['name']}** foi cancelada.\n"
                        f"📝 Motivo: {reason}"
                    )
                except:
                    pass
        
        # Notificar no canal principal
        channel = self.bot.get_channel(RAID_CHANNEL_ID)
        if channel:
            mentions = [f"<@{user_id}>" for user_id in raid['members']]
            await channel.send(
                f"❌ **Raid Cancelada!**\n"
                f"**{boss['name']}** - {' '.join(mentions)}\n"
                f"📝 Motivo: {reason}"
            )
        
        # Atualizar embed final
        await self.update_raid_embed(raid_id)
        
        # Limpar da memória após um tempo
        await asyncio.sleep(60)  # 1 minuto para ver a mensagem
        await self.cleanup_raid(raid_id)
        
        logger.info(f"Raid {raid_id} cancelled: {reason}")
        return True

        
    async def start_ready_check(self, raid_id: int, interaction: discord.Interaction):
        """Inicia ready check para uma raid com sistema melhorado"""
        if raid_id not in self.active_raids:
            return await interaction.response.send_message(
                "❌ Esta raid não existe mais!",
                ephemeral=True
            )
        
        raid = self.active_raids[raid_id]
        
        # Verificar se já há um ready check ativo
        if raid['ready_check_started']:
            return await interaction.response.send_message(
                "❌ Já há um ready check em andamento!",
                ephemeral=True
            )
        
        raid['ready_check_started'] = True
        raid['ready_check_expires'] = datetime.utcnow() + timedelta(minutes=2)
        raid['confirmed_members'] = set()
        
        await interaction.response.send_message(
            "✅ Ready check iniciado! Todos têm 2 minutos para confirmar.",
            ephemeral=True
        )
        
        # Notificar todos os membros no canal principal também
        boss = db.get_boss(raid['boss_id'])
        channel = self.bot.get_channel(RAID_CHANNEL_ID)
        
        mentions = []
        for user_id in raid['members']:
            user = self.bot.get_user(user_id)
            if user:
                mentions.append(user.mention)
                try:
                    await user.send(
                        f"🎯 **READY CHECK INICIADO!**\n"
                        f"O líder iniciou ready check para **{boss['name']}**!\n"
                        f"⏰ Você tem 2 minutos para confirmar presença.\n"
                        f"📋 Clique em **✅ Confirmar** na mensagem da raid no canal de raids."
                    )
                except discord.Forbidden:
                    # Usuário tem DMs fechadas, notificar no canal principal
                    pass
        
        # Notificar no canal principal
        if channel and mentions:
            await channel.send(
                f"🎯 **READY CHECK INICIADO PARA {boss['name']}!**\n"
                f"{' '.join(mentions)}\n"
                f"⏰ Confirmem presença nos próximos 2 minutos!\n"
                f"📋 Cliquem em **✅ Confirmar** na mensagem da raid abaixo.",
                delete_after=120  # Auto-delete após 2 minutos
            )
        
        await self.update_raid_embed(raid_id)

    async def handle_ready_check_confirmation(self, raid_id: int, user_id: int):
        """Processa a confirmação de um membro no ready check"""
        if raid_id not in self.active_raids:
            return False
        
        raid = self.active_raids[raid_id]
        
        if not raid['ready_check_started']:
            return False
        
        if user_id not in raid['members']:
            return False
        
        # Adicionar à lista de confirmados
        raid['confirmed_members'].add(user_id)
        
        # Verificar se todos confirmaram
        if len(raid['confirmed_members']) == len(raid['members']):
            await self.start_raid(raid_id)
            return True
        
        # Verificar se a maioria confirmou (mais de 80%)
        elif len(raid['confirmed_members']) >= len(raid['members']) * 0.8:
            # Notificar líder sobre maioria confirmada
            leader = self.bot.get_user(raid['leader_id'])
            boss = db.get_boss(raid['boss_id'])
            
            if leader:
                try:
                    await leader.send(
                        f"✅ **Maioria confirmada!**\n"
                        f"{len(raid['confirmed_members'])}/{len(raid['members'])} jogadores confirmaram para **{boss['name']}**.\n"
                        f"Você pode iniciar a raid manualmente se desejar."
                    )
                except:
                    pass
        
        await self.update_raid_embed(raid_id)
        return True    
    
    
    # ═══════════════════════════════════════════════════════════════════════════════════════
    # TAREFAS EM BACKGROUND
    # ═══════════════════════════════════════════════════════════════════════════════════════
    

    
    @tasks.loop(minutes=10)  # Intervalo maior
    async def cleanup_task(self):
        """Limpeza menos agressiva de raids"""
        now = datetime.utcnow()
        raids_to_cleanup = []
        
        for raid_id, raid in list(self.active_raids.items()):
            # Limpar apenas raids muito antigas (2 horas) ou concluídas há mais de 30 min
            if raid['status'] == 'recruiting':
                if (now - raid['created_at']).total_seconds() > 7200:  # 2 horas
                    raids_to_cleanup.append(raid_id)
            elif raid['status'] in ['completed', 'failed', 'cancelled']:
                if raid.get('completed_at') and (now - raid['completed_at']).total_seconds() > 1800:  # 30 min
                    raids_to_cleanup.append(raid_id)
            
            # Limpar ready checks expirados (redundante com ready_check_monitor, mas por segurança)
            elif raid['ready_check_started'] and raid['ready_check_expires'] and now > raid['ready_check_expires']:
                raid['ready_check_started'] = False
                raid['confirmed_members'].clear()
                await self.update_raid_embed(raid_id)
        
        # Limpar raids antigas
        for raid_id in raids_to_cleanup:
            await self.cleanup_raid(raid_id)    
    

    @tasks.loop(seconds=10)
    async def voice_monitor(self):
        """Monitora canais de voz para manter sincronização - VERSÃO MELHORADA"""
        for boss_id, voice_channel_id in list(self.voice_queue_channels.items()):
            voice_channel = self.bot.get_channel(voice_channel_id)
            if not voice_channel:
                # Canal foi deletado, limpar
                if boss_id in self.voice_queue_channels:
                    del self.voice_queue_channels[boss_id]
                continue
            
            raid_id = self.voice_channel_raids.get(voice_channel_id)
            if not raid_id or raid_id not in self.active_raids:
                continue
            
            raid = self.active_raids[raid_id]
            
            # Se a raid foi concluída, mover todos de volta
            if raid['status'] in ['completed', 'failed', 'cancelled']:
                required_channel = self.bot.get_channel(REQUIRED_VOICE_CHANNEL_ID)
                if required_channel and voice_channel.members:
                    for member in voice_channel.members:
                        if not member.bot:
                            try:
                                await member.move_to(required_channel)
                            except:
                                pass
                continue
            
            # Verificar se todos os membros da raid estão no canal
            for user_id in raid['members']:
                user = self.bot.get_user(user_id)
                if not user:
                    continue
                    
                # Se usuário não está em nenhum canal de voz, remover da raid
                if not user.voice:
                    await self.remove_member_from_raid(raid_id, user_id)
                    continue
                    
                # Se usuário está em canal diferente do da raid, remover
                if user.voice.channel.id != voice_channel_id:
                    await self.remove_member_from_raid(raid_id, user_id)
                    
                    # Notificar usuário
                    try:
                        boss = db.get_boss(raid['boss_id'])
                        await user.send(
                            f"📤 Você foi removido da fila para **{boss['name']}**\n"
                            f"❌ Motivo: Saiu do canal de voz da raid."
                        )
                    except:
                        pass    
    
    
    @tasks.loop(seconds=15)  # Intervalo maior para reduzir overhead
    async def ready_check_monitor(self):
        """Monitor de ready checks melhorado"""
        now = datetime.utcnow()
        
        for raid_id, raid in list(self.active_raids.items()):
            if raid['ready_check_started'] and raid['ready_check_expires'] and now > raid['ready_check_expires']:
                # Ready check expirou
                raid['ready_check_started'] = False
                
                confirmed_count = len(raid['confirmed_members'])
                total_members = len(raid['members'])
                
                # Para raids públicas e voice queue, ser mais flexível
                if raid.get('auto_ready_check', False):
                    # Se pelo menos 50% confirmou, iniciar raid
                    if confirmed_count >= total_members * 0.5:
                        await self.start_raid(raid_id)
                        continue
                else:
                    # Para raids privadas, exigir mais confirmações
                    if confirmed_count >= total_members * 0.7:
                        await self.start_raid(raid_id)
                        continue
                
                # Ready check falhou
                raid['confirmed_members'].clear()
                await self.update_raid_embed(raid_id)
                
                # Notificar líder
                boss = db.get_boss(raid['boss_id'])
                leader = self.bot.get_user(raid['leader_id'])
                if leader:
                    try:
                        await leader.send(
                            f"⏰ **Ready check expirou!**\n"
                            f"Apenas {confirmed_count}/{total_members} jogadores confirmaram para **{boss['name']}**.\n"
                            f"Você pode iniciar um novo ready check quando quiser."
                        )
                    except:
                        pass

    # ═══════════════════════════════════════════════════════════════════════════════════════
    # COMANDOS ADICIONAIS
    # ═══════════════════════════════════════════════════════════════════════════════════════
    
    @raid_group.command(name="status", description="📊 Mostra status das raids ativas")
    async def raid_status(self, ctx: discord.ApplicationContext):
        """Mostra status de todas as raids ativas"""
        await ctx.defer()
        
        if not self.active_raids:
            return await ctx.followup.send("❌ Nenhuma raid ativa no momento!")
        
        embed = Embed(
            title="📊 STATUS DAS RAIDS ATIVAS",
            color=Color.blue()
        )
        
        active_count = 0
        recruiting_count = 0
        ready_check_count = 0
        
        for raid_id, raid in self.active_raids.items():
            boss = db.get_boss(raid['boss_id'])
            
            if raid['status'] == 'recruiting':
                recruiting_count += 1
                status_emoji = "🔵"
            elif raid['status'] == 'ready_check':
                ready_check_count += 1
                status_emoji = "🟡"
            elif raid['status'] == 'in_progress':
                active_count += 1
                status_emoji = "🟢"
            else:
                continue
            
            embed.add_field(
                name=f"{status_emoji} {boss['name']}",
                value=f"👥 {len(raid['members'])}/{raid['party_size']} | "
                      f"👑 <@{raid['leader_id']}> | "
                      f"🕒 {raid['scheduled_time']}",
                inline=False
            )
        
        embed.set_footer(
            text=f"Total: {len(self.active_raids)} raids | "
                 f"🟢 Ativas: {active_count} | "
                 f"🟡 Ready: {ready_check_count} | "
                 f"🔵 Recrutando: {recruiting_count}"
        )
        
        await ctx.followup.send(embed=embed)
    
    @raid_group.command(name="my_raids", description="👤 Mostra suas raids ativas")
    async def my_raids(self, ctx: discord.ApplicationContext):
        """Mostra raids ativas do usuário"""
        await ctx.defer(ephemeral=True)
        
        user_id = ctx.author.id
        if user_id not in self.user_raids or not self.user_raids[user_id]:
            return await ctx.followup.send("❌ Você não está em nenhuma raid ativa!", ephemeral=True)
        
        embed = Embed(
            title="👤 SUAS RAIDS ATIVAS",
            color=Color.blue()
        )
        
        for raid_id in self.user_raids[user_id]:
            if raid_id not in self.active_raids:
                continue
            
            raid = self.active_raids[raid_id]
            boss = db.get_boss(raid['boss_id'])
            
            status_emoji = {
                'recruiting': '🔵',
                'ready_check': '🟡',
                'in_progress': '🟢',
                'completed': '⚫',
                'cancelled': '🔴'
            }.get(raid['status'], '⚪')
            
            is_leader = raid['leader_id'] == user_id
            leader_text = "👑 (Líder)" if is_leader else ""
            
            embed.add_field(
                name=f"{status_emoji} {boss['name']}",
                value=f"Status: {raid['status'].upper()} {leader_text}\n"
                      f"👥 {len(raid['members'])}/{raid['party_size']} | "
                      f"🕒 {raid['scheduled_time']}",
                inline=False
            )
        
        await ctx.followup.send(embed=embed, ephemeral=True)
    
    @raid_group.command(name="cancel", description="❌ Cancela uma raid que você lidera")
    async def cancel_raid_cmd(self, ctx: discord.ApplicationContext):
        """Cancela uma raid que o usuário lidera"""
        await ctx.defer(ephemeral=True)
        
        user_id = ctx.author.id
        user_raids = []
        
        for raid_id in self.user_raids.get(user_id, []):
            if raid_id in self.active_raids and self.active_raids[raid_id]['leader_id'] == user_id:
                user_raids.append(raid_id)
        
        if not user_raids:
            return await ctx.followup.send("❌ Você não lidera nenhuma raid ativa!", ephemeral=True)
        
        # Se só lidera uma raid, cancelar diretamente
        if len(user_raids) == 1:
            raid_id = user_raids[0]
            await self.cancel_raid(raid_id)
            await ctx.followup.send("✅ Sua raid foi cancelada!", ephemeral=True)
        else:
            # Se lidera múltiplas raids, mostrar seleção
            embed = Embed(
                title="❌ CANCELAR RAID",
                description="Selecione qual raid você quer cancelar:",
                color=Color.red()
            )
            
            view = View(timeout=60)
            select = Select(placeholder="Escolha uma raid para cancelar...")
            
            for raid_id in user_raids:
                raid = self.active_raids[raid_id]
                boss = db.get_boss(raid['boss_id'])
                
                select.add_option(
                    label=f"{boss['name']} ({len(raid['members'])}/{raid['party_size']})",
                    description=f"Criada às {raid['created_at'].strftime('%H:%M')}",
                    value=str(raid_id)
                )
            
            async def cancel_callback(interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message(
                        "❌ Apenas quem abriu pode cancelar!",
                        ephemeral=True
                    )
                
                selected_raid_id = int(select.values[0])
                await self.cancel_raid(selected_raid_id)
                
                await interaction.response.send_message(
                    "✅ Raid cancelada com sucesso!",
                    ephemeral=True
                )
            
            select.callback = cancel_callback
            view.add_item(select)
            
            await ctx.followup.send(embed=embed, view=view, ephemeral=True)


    async def complete_raid(self, raid_id: int, success: bool = True, interaction: discord.Interaction = None):
        """Marca uma raid como completada com sistema melhorado"""
        if raid_id not in self.active_raids:
            if interaction:
                await interaction.response.send_message(
                    "❌ Esta raid não existe mais!",
                    ephemeral=True
                )
            return
        
        raid = self.active_raids[raid_id]
        boss = db.get_boss(raid['boss_id'])
        
        # Verificar permissões
        if interaction and interaction.user.id != raid['leader_id']:
            await interaction.response.send_message(
                "❌ Apenas o líder pode marcar a raid como concluída!",
                ephemeral=True
            )
            return
        
        raid['status'] = 'completed' if success else 'failed'
        raid['completed_at'] = datetime.utcnow()
        
        # Notificar todos os membros
        mentions = []
        original_channels = {}  # Armazenar canais originais para retorno
        
        for user_id in raid['members']:
            user = self.bot.get_user(user_id)
            if user:
                mentions.append(user.mention)
                
                # Armazenar canal original se estiver em canal de voz da raid
                if user.voice and user.voice.channel:
                    voice_channel_id = self.voice_queue_channels.get(raid['boss_id'])
                    if user.voice.channel.id == voice_channel_id:
                        original_channels[user_id] = REQUIRED_VOICE_CHANNEL_ID
                
                try:
                    status_emoji = "🎉" if success else "❌"
                    status_text = "CONCLUÍDA COM SUCESSO" if success else "FALHOU"
                    
                    await user.send(
                        f"{status_emoji} **RAID {status_text}!**\n"
                        f"A raid para **{boss['name']}** foi {'concluída' if success else 'falhou'}.\n"
                        f"🕒 Duração: {(raid['completed_at'] - raid['started_at']).total_seconds() // 60:.0f} minutos\n"
                        f"👥 Participantes: {len(raid['members'])} jogadores"
                    )
                except:
                    pass
        
        # Mover jogadores de volta para o canal original
        required_channel = self.bot.get_channel(REQUIRED_VOICE_CHANNEL_ID)
        if required_channel:
            for user_id, original_channel_id in original_channels.items():
                user = self.bot.get_user(user_id)
                if user and user.voice:
                    try:
                        await user.move_to(required_channel)
                    except:
                        pass
        
        # Notificar no canal principal
        channel = self.bot.get_channel(RAID_CHANNEL_ID)
        if channel and mentions:
            status_emoji = "🎉" if success else "❌"
            status_text = "CONCLUÍDA COM SUCESSO" if success else "FALHOU"
            
            await channel.send(
                f"{status_emoji} **RAID {status_text}!**\n"
                f"**{boss['name']}** - {' '.join(mentions)}\n"
                f"🏆 {status_text}! {'Parabéns pelo loot!' if success else 'Melhor sorte na próxima!'}"
            )
        
        # Limpar recursos associados
        if raid['is_voice_queue'] and raid['boss_id'] in self.voice_queue_channels:
            voice_channel_id = self.voice_queue_channels[raid['boss_id']]
            if voice_channel_id in self.voice_channel_raids:
                del self.voice_channel_raids[voice_channel_id]
            
            # Deletar canal de voz após um tempo
            voice_channel = self.bot.get_channel(voice_channel_id)
            if voice_channel:
                # Esperar jogadores saírem naturalmente
                await asyncio.sleep(30)
                
                # Mover jogadores restantes para canal principal
                if voice_channel.members:
                    for member in voice_channel.members:
                        if not member.bot:
                            try:
                                await member.move_to(required_channel)
                            except:
                                pass
                
                # Deletar canal
                try:
                    await voice_channel.delete(reason=f"Raid {raid_id} completed")
                except:
                    pass
        
        await self.update_raid_embed(raid_id)
        
        if interaction:
            await interaction.response.send_message(
                f"✅ Raid marcada como {'concluída' if success else 'falhou'}!",
                ephemeral=True
            )
        
        # Limpar da memória após um tempo
        await asyncio.sleep(300)  # 5 minutos
        await self.cleanup_raid(raid_id)

def setup(bot: commands.Bot):
    """Setup do cog"""
    bot.add_cog(RaidBuilderSystem(bot))
    logger.info("RaidBuilderSystem cog loaded successfully!")