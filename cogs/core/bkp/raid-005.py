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
        self.raid_threads: Dict[int, int] = {}  
        
        # Iniciar tarefas em background
        self.cleanup_task.start()
        self.voice_monitor.start()
        self.ready_check_monitor.start()
    
    def cog_unload(self):
        """Limpar tarefas ao descarregar cog"""
        self.cleanup_task.cancel()
        self.voice_monitor.cancel()
        self.ready_check_monitor.cancel()
    
    async def cog_load(self):
        """Executado quando o cog é carregado"""
        logger.info("RaidBuilderSystem cog loaded - starting background tasks")
    
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
        
        # Notificar na thread da raid
        mentions = []
        for user_id in raid['members']:
            user = self.bot.get_user(user_id)
            if user:
                mentions.append(user.mention)
        
        if mentions:
            thread_message = await self.send_to_raid_thread(
                raid_id,
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
        raid['ready_check_expires'] = datetime.utcnow() + timedelta(minutes=1)
        raid['confirmed_members'].clear()
        
        # Atualizar embed - IMPORTANTE: isso faz os botões aparecerem
        await self.update_raid_embed(raid_id)
        
        # Notificar na thread da raid
        boss = db.get_boss(raid['boss_id'])
        
        mentions = []
        for user_id in raid['members']:
            user = self.bot.get_user(user_id)
            if user:
                mentions.append(user.mention)
        
        await self.send_to_raid_thread(
            raid_id,
            f"🎯 **READY CHECK AUTOMÁTICO!**\n"
            f"🎮 Boss: **{boss['name']}**\n"
            f"⏰ Vocês têm 1 minuto para confirmar presença!\n"
            f"📋 Cliquem em **✅ Confirmar** na mensagem da raid.\n\n"
            f"{' '.join(mentions)}",
            mention_role=True
        )
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
        @tasks.loop(seconds=30)
        async def cleanup_raid(self, raid_id: int):
            """Limpa completamente uma raid da memória"""
            if raid_id not in self.active_raids:
                return
            
            raid = self.active_raids[raid_id]
            
            # Deletar canal de voz se for uma raid de voice queue
            if raid.get('is_voice_queue') and raid['boss_id'] in self.voice_queue_channels:
                voice_channel_id = self.voice_queue_channels[raid['boss_id']]
                voice_channel = self.bot.get_channel(voice_channel_id)
                
                if voice_channel:
                    try:
                        await voice_channel.delete(reason=f"Raid {raid_id} cleanup")
                        logger.info(f"Canal de voz {voice_channel_id} deletado durante cleanup da raid {raid_id}")
                    except Exception as e:
                        logger.error(f"Erro ao deletar canal de voz durante cleanup: {e}")
                
                # Limpar associações
                if raid['boss_id'] in self.voice_queue_channels:
                    del self.voice_queue_channels[raid['boss_id']]
                if voice_channel_id in self.voice_channel_raids:
                    del self.voice_channel_raids[voice_channel_id]
            
            # Resto do código de limpeza...
            # Remover de índices de usuários
            for user_id in raid['members']:
                if user_id in self.user_raids:
                    self.user_raids[user_id].discard(raid_id)
                    if not self.user_raids[user_id]:
                        del self.user_raids[user_id]
            
            # Remover referências de mensagens
            if raid_id in self.raid_messages:
                del self.raid_messages[raid_id]
            
            # Remover referência da thread
            if raid_id in self.raid_threads:
                del self.raid_threads[raid_id]
            
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
            
            # Enviar embed da raid e criar thread
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

        async def send_raid_embed(self, raid_data: Dict, channel: discord.TextChannel):
            """Versão corrigida do envio de embed de raid"""
            try:
                boss = db.get_boss(raid_data['boss_id'])
                leader = self.bot.get_user(raid_data['leader_id'])
                
                if not boss or not leader:
                    logger.error(f"Boss or leader not found for raid {raid_data['id']}")
                    return
                
                # Criar embed
                embed = self.create_raid_embed(raid_data, boss, leader)
                
                # Criar view com botões
                view = self.create_raid_view(raid_data)
                
                # Enviar mensagem
                message = await channel.send(embed=embed, view=view)
                
                # Armazenar referência da mensagem
                self.raid_messages[raid_data['id']] = {
                    'message_id': message.id,
                    'channel_id': channel.id
                }
                
                # Criar thread para a raid - CORREÇÃO AQUI
                try:
                    thread_name = f"🎯 {boss['name']} - Raid {raid_data['id']}"
                    thread = await message.create_thread(
                        name=thread_name[:100],  # Limite de caracteres do Discord
                        auto_archive_duration=60  # 1 hora
                    )
                    
                    self.raid_threads[raid_data['id']] = thread.id
                    
                    # Mensagem inicial na thread
                    welcome_msg = (
                        f"🎉 **Raid criada por {leader.mention}!**\n"
                        f"🎮 **Boss:** {boss['name']}\n"
                        f"👥 **Tamanho:** {len(raid_data['members'])}/{raid_data['party_size']}\n"
                        f"📋 **Descrição:** {raid_data['description']}\n"
                        f"⏰ **Horário:** {raid_data['scheduled_time']}\n\n"
                        f"💬 Use esta thread para comunicação durante a raid!\n"
                        f"📢 O líder pode usar `/raid invite` para convidar jogadores."
                    )
                    
                    await thread.send(welcome_msg)
                    
                except Exception as e:
                    logger.error(f"Error creating thread for raid {raid_data['id']}: {e}")
                    # Continuar mesmo se falhar a thread
                
                return message
                
            except Exception as e:
                logger.error(f"Error sending raid embed: {e}")
                return None

        def create_raid_embed(self, raid_data: Dict, boss: Dict, leader: discord.User) -> Embed:
            """Cria embed para raid"""
            color = Color.green() if raid_data['status'] == 'recruiting' else Color.orange()
            
            embed = Embed(
                title=f"🎯 {boss['name']}",
                description=raid_data['description'],
                color=color,
                timestamp=datetime.utcnow()
            )
            
            # Informações básicas
            embed.add_field(
                name="👥 Grupo",
                value=f"{len(raid_data['members'])}/{raid_data['party_size']} jogadores",
                inline=True
            )
            
            embed.add_field(
                name="🎮 Dificuldade",
                value=f"{boss['difficulty']}/5 ⭐",
                inline=True
            )
            
            embed.add_field(
                name="🗺️ Mapa",
                value=boss['map'],
                inline=True
            )
            
            # Líder e horário
            embed.add_field(
                name="👑 Líder",
                value=leader.mention,
                inline=True
            )
            
            embed.add_field(
                name="⏰ Horário",
                value=raid_data['scheduled_time'],
                inline=True
            )
            
            # Status
            status_emoji = {
                'recruiting': '🟢',
                'ready_check': '🟡',
                'in_progress': '🟠',
                'completed': '🟣',
                'failed': '🔴'
            }
            
            embed.add_field(
                name="📊 Status",
                value=f"{status_emoji.get(raid_data['status'], '⚪')} {raid_data['status'].upper()}",
                inline=True
            )
            
            # Membros
            members_text = []
            for user_id in raid_data['members']:
                user = self.bot.get_user(user_id)
                status = "✅" if user_id in raid_data['confirmed_members'] else "⏳"
                members_text.append(f"{status} {user.mention if user else f'<@{user_id}>'}")
            
            embed.add_field(
                name=f"🎮 Jogadores ({len(raid_data['members'])}/{raid_data['party_size']})",
                value="\n".join(members_text) if members_text else "Nenhum jogador ainda",
                inline=False
            )
            
            # Footer com ID da raid
            embed.set_footer(text=f"Raid ID: {raid_data['id']} • Criada em")
            
            return embed

    def create_raid_view(self, raid_data: Dict) -> View:
        """Cria view com botões para a raid - CORREÇÃO: garantir que botões de ready check apareçam"""
        view = View(timeout=None)
        
        # Botões baseados no status
        if raid_data['status'] == 'recruiting':
            join_btn = Button(
                style=ButtonStyle.green,
                label="🎮 Entrar",
                custom_id=f"raid_join_{raid_data['id']}"
            )
            join_btn.callback = lambda i: self.join_raid_callback(i, raid_data['id'])
            view.add_item(join_btn)
            
            leave_btn = Button(
                style=ButtonStyle.red,
                label="🚪 Sair",
                custom_id=f"raid_leave_{raid_data['id']}"
            )
            leave_btn.callback = lambda i: self.leave_raid_callback(i, raid_data['id'])
            view.add_item(leave_btn)
            
            if raid_data['leader_id'] == self.bot.user.id or not raid_data['is_private']:
                invite_btn = Button(
                    style=ButtonStyle.blurple,
                    label="📨 Convidar",
                    custom_id=f"raid_invite_{raid_data['id']}"
                )
                invite_btn.callback = lambda i: self.invite_callback(i, raid_data['id'])
                view.add_item(invite_btn)
        
        elif raid_data['status'] == 'ready_check' or raid_data.get('ready_check_started', False):
            # MOSTRAR BOTÕES DE READY CHECK MESMO QUE O STATUS AINDA SEJA RECRUITING
            confirm_btn = Button(
                style=ButtonStyle.green,
                label="✅ Confirmar",
                custom_id=f"raid_confirm_{raid_data['id']}"
            )
            confirm_btn.callback = lambda i: self.confirm_callback(i, raid_data['id'])
            view.add_item(confirm_btn)
            
            unconfirm_btn = Button(
                style=ButtonStyle.red,
                label="❌ Não Vou",
                custom_id=f"raid_unconfirm_{raid_data['id']}"
            )
            unconfirm_btn.callback = lambda i: self.unconfirm_callback(i, raid_data['id'])
            view.add_item(unconfirm_btn)
        
        elif raid_data['status'] == 'in_progress':
            complete_btn = Button(
                style=ButtonStyle.green,
                label="✅ Concluir",
                custom_id=f"raid_complete_{raid_data['id']}"
            )
            complete_btn.callback = lambda i: self.complete_callback(i, raid_data['id'])
            view.add_item(complete_btn)
            
            fail_btn = Button(
                style=ButtonStyle.red,
                label="❌ Falhou",
                custom_id=f"raid_fail_{raid_data['id']}"
            )
            fail_btn.callback = lambda i: self.fail_callback(i, raid_data['id'])
            view.add_item(fail_btn)
        
        return view

        # ═══════════════════════════════════════════════════════════════════════════════════════
        # CALLBACKS DOS BOTÕES
        # ═══════════════════════════════════════════════════════════════════════════════════════
    async def unconfirm_callback(self, interaction: discord.Interaction, raid_id: int):
        """Callback para botão de não vou - remove da raid"""
        if raid_id not in self.active_raids:
            return await interaction.response.send_message(
                "❌ Esta raid não existe mais!",
                ephemeral=True
            )
        
        raid = self.active_raids[raid_id]
        
        # Verificar se está na raid
        if interaction.user.id not in raid['members']:
            return await interaction.response.send_message(
                "❌ Você não está nesta raid!",
                ephemeral=True
            )
        
        # Remover da raid
        await self.remove_member_from_raid(raid_id, interaction.user.id)
        
        await interaction.response.send_message(
            "❌ Você foi removido da raid.",
            ephemeral=True
        )
        
        # Mover de volta para canal original se estiver em canal de voz
        required_channel = self.bot.get_channel(REQUIRED_VOICE_CHANNEL_ID)
        if required_channel and interaction.user.voice and interaction.user.voice.channel:
            try:
                await interaction.user.move_to(required_channel)
            except Exception as e:
                logger.error(f"Error moving user back to original channel: {e}")
        async def join_raid_callback(self, interaction: discord.Interaction, raid_id: int):
            """Callback para botão de entrar na raid - move para canal de voz"""
            if raid_id not in self.active_raids:
                return await interaction.response.send_message(
                    "❌ Esta raid não existe mais!",
                    ephemeral=True
                )
            
            raid = self.active_raids[raid_id]
            
            # Verificar se já está na raid
            if interaction.user.id in raid['members']:
                return await interaction.response.send_message(
                    "❌ Você já está nesta raid!",
                    ephemeral=True
                )
            
            # Verificar se está cheia
            if len(raid['members']) >= raid['party_size']:
                return await interaction.response.send_message(
                    "❌ A raid está cheia!",
                    ephemeral=True
                )
            
            # Verificar se é uma raid de voice queue
            if raid.get('is_voice_queue') and raid['boss_id'] in self.voice_queue_channels:
                voice_channel_id = self.voice_queue_channels[raid['boss_id']]
                voice_channel = self.bot.get_channel(voice_channel_id)
                
                if voice_channel:
                    # Verificar se o usuário está em algum canal de voz
                    if not interaction.user.voice or not interaction.user.voice.channel:
                        return await interaction.response.send_message(
                            "❌ Você precisa estar em um canal de voz para entrar nesta raid!",
                            ephemeral=True
                        )
                    
                    try:
                        # Mover usuário para o canal de voz da raid
                        await interaction.user.move_to(voice_channel)
                        # O membro será adicionado automaticamente pelo voice monitor
                        await interaction.response.send_message(
                            f"✅ Você foi movido para o canal de voz da raid **{db.get_boss(raid['boss_id'])['name']}**!",
                            ephemeral=True
                        )
                    except Exception as e:
                        logger.error(f"Error moving user to voice channel: {e}")
                        return await interaction.response.send_message(
                            "❌ Erro ao mover para o canal de voz!",
                            ephemeral=True
                        )
                else:
                    return await interaction.response.send_message(
                        "❌ Canal de voz não encontrado!",
                        ephemeral=True
                    )
            else:
                # Para raids normais, apenas adicionar à raid
                success = await self.add_member_to_raid(raid_id, interaction.user.id)
                if success:
                    await interaction.response.send_message(
                        f"✅ Você entrou na raid para **{db.get_boss(raid['boss_id'])['name']}**!",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "❌ Não foi possível entrar na raid!",
                        ephemeral=True
                    )
        
        
        async def leave_raid_callback(self, interaction: discord.Interaction, raid_id: int):
            """Callback para botão de sair da raid"""
            if raid_id not in self.active_raids:
                return await interaction.response.send_message(
                    "❌ Esta raid não existe mais!",
                    ephemeral=True
                )
            
            raid = self.active_raids[raid_id]
            
            # Verificar se está na raid
            if interaction.user.id not in raid['members']:
                return await interaction.response.send_message(
                    "❌ Você não está nesta raid!",
                    ephemeral=True
                )
            
            # Não permitir que o líder saia (deve cancelar a raid)
            if interaction.user.id == raid['leader_id']:
                return await interaction.response.send_message(
                    "❌ Você é o líder! Use `/raid cancel` para cancelar a raid.",
                    ephemeral=True
                )
            
            # Remover da raid
            await self.remove_member_from_raid(raid_id, interaction.user.id)
            
            await interaction.response.send_message(
                f"📤 Você saiu da raid para **{db.get_boss(raid['boss_id'])['name']}**.",
                ephemeral=True
            )
        
        async def invite_callback(self, interaction: discord.Interaction, raid_id: int):
            """Callback para botão de convidar"""
            if raid_id not in self.active_raids:
                return await interaction.response.send_message(
                    "❌ Esta raid não existe mais!",
                    ephemeral=True
                )
            
            raid = self.active_raids[raid_id]
            
            # Verificar permissões
            if interaction.user.id != raid['leader_id'] and interaction.user.id != self.bot.user.id:
                return await interaction.response.send_message(
                    "❌ Apenas o líder pode convidar jogadores!",
                    ephemeral=True
                )
            
            # Abrir modal de convite
            modal = InviteModal(raid_id, self)
            await interaction.response.send_modal(modal)
            
    async def confirm_callback(self, interaction: discord.Interaction, raid_id: int):
        """Callback para botão de confirmar presença"""
        if raid_id not in self.active_raids:
            return await interaction.response.send_message(
                "❌ Esta raid não existe mais!",
                ephemeral=True
            )
        
        raid = self.active_raids[raid_id]
        
        # Verificar se está na raid
        if interaction.user.id not in raid['members']:
            return await interaction.response.send_message(
                "❌ Você não está nesta raid!",
                ephemeral=True
            )
        
        # Verificar se o ready check está ativo
        if not raid['ready_check_started']:
            return await interaction.response.send_message(
                "❌ Não há ready check ativo no momento!",
                ephemeral=True
            )
        
        # Confirmar presença
        raid['confirmed_members'].add(interaction.user.id)
        
        await interaction.response.send_message(
            "✅ Presença confirmada! Aguarde o início da raid.",
            ephemeral=True
        )
        
        # Atualizar embed para mostrar que confirmou
        await self.update_raid_embed(raid_id)
        
        # Verificar se todos confirmaram
        if len(raid['confirmed_members']) == len(raid['members']):
            await self.start_raid(raid_id)
        
        
        async def complete_callback(self, interaction: discord.Interaction, raid_id: int):
            """Callback para botão de concluir raid"""
            if raid_id not in self.active_raids:
                return await interaction.response.send_message(
                    "❌ Esta raid não existe mais!",
                    ephemeral=True
                )
            
            raid = self.active_raids[raid_id]
            
            # Verificar permissões
            if interaction.user.id != raid['leader_id']:
                return await interaction.response.send_message(
                    "❌ Apenas o líder pode concluir a raid!",
                    ephemeral=True
                )
            
            await self.complete_raid(raid_id, True, interaction)
        
        async def fail_callback(self, interaction: discord.Interaction, raid_id: int):
            """Callback para botão de falhar raid"""
            if raid_id not in self.active_raids:
                return await interaction.response.send_message(
                    "❌ Esta raid não existe mais!",
                    ephemeral=True
                )
            
            raid = self.active_raids[raid_id]
            
            # Verificar permissões
            if interaction.user.id != raid['leader_id']:
                return await interaction.response.send_message(
                    "❌ Apenas o líder pode marcar a raid como falha!",
                    ephemeral=True
                )
            
            await self.complete_raid(raid_id, False, interaction)

        # ═══════════════════════════════════════════════════════════════════════════════════════
        # GERENCIAMENTO DE MEMBROS
        # ═══════════════════════════════════════════════════════════════════════════════════════
        
        async def add_member_to_raid(self, raid_id: int, user_id: int):
            """Adiciona membro à raid"""
            if raid_id not in self.active_raids:
                return False
            
            raid = self.active_raids[raid_id]
            
            # Verificar se já está na raid
            if user_id in raid['members']:
                return False
            
            # Verificar se está cheia
            if len(raid['members']) >= raid['party_size']:
                return False
            
            # Adicionar à raid
            raid['members'].append(user_id)
            
            # Atualizar índice de usuário
            if user_id not in self.user_raids:
                self.user_raids[user_id] = set()
            self.user_raids[user_id].add(raid_id)
            
            # Atualizar embed
            await self.update_raid_embed(raid_id)
            
            logger.info(f"User {user_id} added to raid {raid_id}")
            return True
        
        async def remove_member_from_raid(self, raid_id: int, user_id: int):
            """Remove membro da raid"""
            if raid_id not in self.active_raids:
                return False
            
            raid = self.active_raids[raid_id]
            
            # Verificar se está na raid
            if user_id not in raid['members']:
                return False
            
            # Não permitir remover o líder
            if user_id == raid['leader_id']:
                return False
            
            # Remover da raid
            raid['members'].remove(user_id)
            
            # Remover de confirmados se estiver lá
            if user_id in raid['confirmed_members']:
                raid['confirmed_members'].discard(user_id)
            
            # Atualizar índice de usuário
            if user_id in self.user_raids:
                self.user_raids[user_id].discard(raid_id)
                if not self.user_raids[user_id]:
                    del self.user_raids[user_id]
            
            # Se a raid ficar vazia (apenas líder), cancelar
            if len(raid['members']) <= 1 and raid['status'] == 'recruiting':
                await self.cancel_raid(raid_id)
                return True
            
            # Atualizar embed
            await self.update_raid_embed(raid_id)
            
            logger.info(f"User {user_id} removed from raid {raid_id}")
            return True

        # ═══════════════════════════════════════════════════════════════════════════════════════
        # GERENCIAMENTO DE RAID
        # ═══════════════════════════════════════════════════════════════════════════════════════
        
        async def start_raid(self, raid_id: int):
            """Inicia a raid"""
            if raid_id not in self.active_raids:
                return
            
            raid = self.active_raids[raid_id]
            boss = db.get_boss(raid['boss_id'])
            
            # Atualizar status
            raid['status'] = 'in_progress'
            raid['started_at'] = datetime.utcnow()
            raid['ready_check_started'] = False
            raid['ready_check_expires'] = None
            
            # Atualizar embed
            await self.update_raid_embed(raid_id)
            
            # Notificar na thread
            await self.send_to_raid_thread(
                raid_id,
                f"🚀 **RAID INICIADA!**\n"
                f"🎯 Boss: **{boss['name']}**\n"
                f"👥 Grupo: {len(raid['members'])}/{raid['party_size']} jogadores\n"
                f"⏰ Iniciada às {datetime.utcnow().strftime('%H:%M:%S')} UTC\n\n"
                f"🎮 Boa sorte! Use os botões abaixo para marcar como concluída ou falha."
            )
            
            logger.info(f"Raid {raid_id} started for boss {boss['name']}")
        
        async def complete_raid(self, raid_id: int, success: bool, interaction: discord.Interaction = None):
            """Completa a raid com sucesso ou falha"""
            if raid_id not in self.active_raids:
                if interaction:
                    try:
                        await interaction.response.send_message(
                            "❌ Esta raid não existe mais!",
                            ephemeral=True
                        )
                    except discord.errors.NotFound:
                        pass
                return
            
            raid = self.active_raids[raid_id]
            boss = db.get_boss(raid['boss_id'])
            
            # Atualizar status
            raid['status'] = 'completed' if success else 'failed'
            raid['completed_at'] = datetime.utcnow()
            
            # Enviar mensagem de resultado
            result_msg = (
                f"🎉 **RAID CONCLUÍDA COM SUCESSO!**\n"
                f"🏆 Boss: **{boss['name']}** derrotado!\n"
                f"👥 Grupo: {len(raid['members'])} jogadores\n"
                f"⏰ Duração: {self.format_duration(raid['started_at'], raid['completed_at'])}\n\n"
                f"✨ Parabéns a todos os participantes!"
            ) if success else (
                f"💀 **RAID FALHOU!**\n"
                f"☠️ Boss: **{boss['name']}** não foi derrotado\n"
                f"👥 Grupo: {len(raid['members'])} jogadores\n"
                f"⏰ Duração: {self.format_duration(raid['started_at'], raid['completed_at'])}\n\n"
                f"😔 Melhor sorte na próxima vez!"
            )
            
            # Tentar responder à interação se fornecida
            if interaction:
                try:
                    await interaction.response.send_message(
                        result_msg,
                        ephemeral=True
                    )
                except discord.errors.NotFound:
                    # Interação expirada, enviar para a thread
                    await self.send_to_raid_thread(raid_id, result_msg)
                except Exception as e:
                    logger.error(f"Error responding to interaction: {e}")
                    await self.send_to_raid_thread(raid_id, result_msg)
            else:
                await self.send_to_raid_thread(raid_id, result_msg)
            
            # Atualizar embed
            await self.update_raid_embed(raid_id)
            
            # Limpar recursos da raid
            await self.cleanup_raid_resources(raid_id)
            
            logger.info(f"Raid {raid_id} completed - Success: {success}")
    
        async def cleanup_raid_resources(self, raid_id: int):
            """Limpa recursos da raid após conclusão - move jogadores de volta"""
            if raid_id not in self.active_raids:
                return
            
            raid = self.active_raids[raid_id]
            
            # Mover todos os membros de volta para o canal original
            required_channel = self.bot.get_channel(REQUIRED_VOICE_CHANNEL_ID)
            if required_channel:
                for user_id in raid['members']:
                    user = self.bot.get_user(user_id)
                    if user and user.voice and user.voice.channel:
                        try:
                            await user.move_to(required_channel)
                        except Exception as e:
                            logger.error(f"Error moving user {user_id} back to original channel: {e}")
            
            # Deletar canal de voz se for uma raid de voice queue
            if raid.get('is_voice_queue') and raid['boss_id'] in self.voice_queue_channels:
                voice_channel_id = self.voice_queue_channels[raid['boss_id']]
                voice_channel = self.bot.get_channel(voice_channel_id)
                
                if voice_channel:
                    try:
                        # Mover quaisquer membros restantes para o canal original
                        for member in voice_channel.members:
                            if not member.bot:
                                try:
                                    await member.move_to(required_channel)
                                except:
                                    pass
                        
                        await voice_channel.delete(reason=f"Raid {raid_id} completed")
                        logger.info(f"Voice channel {voice_channel_id} deleted after raid {raid_id} completion")
                    except Exception as e:
                        logger.error(f"Error deleting voice channel: {e}")
                
                # Limpar associações
                if raid['boss_id'] in self.voice_queue_channels:
                    del self.voice_queue_channels[raid['boss_id']]
                if voice_channel_id in self.voice_channel_raids:
                    del self.voice_channel_raids[voice_channel_id]
            
            # Agendar limpeza completa
            await asyncio.sleep(300)  # 5 minutos
            await self.cleanup_raid(raid_id)    
        async def cancel_raid(self, raid_id: int):
            """Cancela a raid"""
            if raid_id not in self.active_raids:
                return
            
            raid = self.active_raids[raid_id]
            boss = db.get_boss(raid['boss_id'])
            
            # Notificar cancelamento
            await self.send_to_raid_thread(
                raid_id,
                f"❌ **RAID CANCELADA!**\n"
                f"🎯 Boss: **{boss['name']}**\n"
                f"👥 Grupo: {len(raid['members'])}/{raid['party_size']} jogadores\n"
                f"📋 Motivo: Não há jogadores suficientes ou líder desistiu."
            )
            
            # Limpar recursos
            await self.cleanup_raid_resources(raid_id)
            
            logger.info(f"Raid {raid_id} cancelled")

        # ═══════════════════════════════════════════════════════════════════════════════════════
        # TAREFAS EM BACKGROUND
        # ═══════════════════════════════════════════════════════════════════════════════════════
        
        @tasks.loop(minutes=5)
        async def cleanup_task(self):
            """Tarefa de limpeza periódica"""
            try:
                current_time = datetime.utcnow()
                raids_to_cleanup = []
                
                # Verificar raids expiradas
                for raid_id, raid in list(self.active_raids.items()):
                    # Ready checks expirados
                    if (raid['ready_check_started'] and 
                        raid['ready_check_expires'] and 
                        current_time > raid['ready_check_expires']):
                        
                        # Verificar quantos confirmaram
                        confirmed_count = len(raid['confirmed_members'])
                        total_count = len(raid['members'])
                        
                        if confirmed_count < total_count:
                            # Ready check falhou
                            await self.send_to_raid_thread(
                                raid_id,
                                f"⏰ **READY CHECK EXPIRADO!**\n"
                                f"✅ Confirmados: {confirmed_count}/{total_count}\n"
                                f"❌ A raid foi cancelada devido à falta de confirmações."
                            )
                            raids_to_cleanup.append(raid_id)
                    
                    # Raids inativas por muito tempo (mais de 2 horas)
                    elif (raid['status'] == 'recruiting' and 
                        (current_time - raid['created_at']).total_seconds() > 7200):
                        raids_to_cleanup.append(raid_id)
                
                # Limpar raids expiradas
                for raid_id in raids_to_cleanup:
                    await self.cleanup_raid(raid_id)
                    
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
        
        @tasks.loop(seconds=30)
        async def voice_monitor(self):
            """Monitora canais de voz para manter sincronia"""
            try:
                for voice_channel_id, raid_id in list(self.voice_channel_raids.items()):
                    if raid_id not in self.active_raids:
                        continue
                    
                    voice_channel = self.bot.get_channel(voice_channel_id)
                    if not voice_channel:
                        continue
                    
                    raid = self.active_raids[raid_id]
                    
                    # Verificar membros no canal vs membros na raid
                    voice_members = {m.id for m in voice_channel.members if not m.bot}
                    raid_members = set(raid['members'])
                    
                    # Adicionar quem está no canal mas não na raid
                    for user_id in voice_members - raid_members:
                        if len(raid['members']) < raid['party_size']:
                            await self.add_member_to_raid(raid_id, user_id)
                    
                    # Remover quem não está mais no canal (apenas se raid ainda recrutando)
                    if raid['status'] == 'recruiting':
                        for user_id in raid_members - voice_members:
                            if user_id != raid['leader_id']:  # Não remover líder
                                await self.remove_member_from_raid(raid_id, user_id)
                                
            except Exception as e:
                logger.error(f"Error in voice monitor: {e}")
        
        @tasks.loop(seconds=30)
        async def ready_check_monitor(self):
            """Monitora ready checks expirando - remove quem não confirmou"""
            try:
                current_time = datetime.utcnow()
                
                for raid_id, raid in list(self.active_raids.items()):
                    if (raid['ready_check_started'] and 
                        raid['ready_check_expires'] and 
                        current_time > raid['ready_check_expires']):
                        
                        # Ready check expirou
                        confirmed_count = len(raid['confirmed_members'])
                        total_count = len(raid['members'])
                        
                        if confirmed_count == total_count:
                            # Todos confirmaram, iniciar raid
                            await self.start_raid(raid_id)
                        else:
                            # Remover quem não confirmou
                            unconfirmed_users = []
                            for user_id in list(raid['members']):
                                if user_id != raid['leader_id'] and user_id not in raid['confirmed_members']:
                                    unconfirmed_users.append(user_id)
                                    await self.remove_member_from_raid(raid_id, user_id)
                            
                            # Mover usuários não confirmados de volta para canal original
                            required_channel = self.bot.get_channel(REQUIRED_VOICE_CHANNEL_ID)
                            if required_channel and unconfirmed_users:
                                for user_id in unconfirmed_users:
                                    user = self.bot.get_user(user_id)
                                    if user and user.voice and user.voice.channel:
                                        try:
                                            await user.move_to(required_channel)
                                        except:
                                            pass
                            
                            # Notificar na thread
                            unconfirmed_mentions = []
                            for user_id in unconfirmed_users:
                                user = self.bot.get_user(user_id)
                                if user:
                                    unconfirmed_mentions.append(user.mention)
                            
                            await self.send_to_raid_thread(
                                raid_id,
                                f"⏰ **READY CHECK EXPIRADO!**\n"
                                f"✅ Confirmados: {confirmed_count}/{total_count}\n"
                                f"❌ Removidos por não confirmar: {', '.join(unconfirmed_mentions) if unconfirmed_mentions else 'Ninguém'}\n"
                                f"🔄 Continuando recrutamento..."
                            )
                            
                            # Resetar ready check
                            raid['ready_check_started'] = False
                            raid['ready_check_expires'] = None
                            raid['confirmed_members'].clear()
                            
                            # Atualizar embed
                            await self.update_raid_embed(raid_id)
                            
            except Exception as e:
                logger.error(f"Error in ready check monitor: {e}")
                
        @cleanup_task.before_loop
        @voice_monitor.before_loop
        @ready_check_monitor.before_loop
        async def before_tasks(self):
            """Esperar o bot ficar pronto antes de iniciar tarefas"""
            await self.bot.wait_until_ready()

        # ═══════════════════════════════════════════════════════════════════════════════════════
        # UTILITÁRIOS
        # ═══════════════════════════════════════════════════════════════════════════════════════
        
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
                
                boss = db.get_boss(raid['boss_id'])
                leader = self.bot.get_user(raid['leader_id'])
                
                if not boss or not leader:
                    return
                
                # Criar novo embed e view
                embed = self.create_raid_embed(raid, boss, leader)
                view = self.create_raid_view(raid)
                
                await message.edit(embed=embed, view=view)
                
            except Exception as e:
                logger.error(f"Error updating raid embed {raid_id}: {e}")
        
        async def send_to_raid_thread(self, raid_id: int, message: str, mention_role: bool = False):
            """Envia mensagem para a thread da raid"""
            if raid_id not in self.raid_threads:
                return None
            
            try:
                thread = self.bot.get_channel(self.raid_threads[raid_id])
                if not thread:
                    return None
                
                # Se for para mencionar, mencionar todos os membros
                if mention_role and raid_id in self.active_raids:
                    raid = self.active_raids[raid_id]
                    mentions = []
                    for user_id in raid['members']:
                        user = self.bot.get_user(user_id)
                        if user:
                            mentions.append(user.mention)
                    
                    if mentions:
                        message = f"{' '.join(mentions)}\n{message}"
                
                return await thread.send(message)
                
            except Exception as e:
                logger.error(f"Error sending to raid thread {raid_id}: {e}")
                return None
        
        async def send_raid_invite(self, raid_id: int, user: discord.User, inviter: discord.User):
            """Envia convite de raid para um usuário"""
            if raid_id not in self.active_raids:
                return False
            
            raid = self.active_raids[raid_id]
            boss = db.get_boss(raid['boss_id'])
            
            try:
                embed = Embed(
                    title=f"🎯 Convite de Raid - {boss['name']}",
                    description=(
                        f"📋 **Descrição:** {raid['description']}\n"
                        f"👑 **Líder:** {inviter.mention}\n"
                        f"👥 **Tamanho:** {len(raid['members'])}/{raid['party_size']}\n"
                        f"⏰ **Horário:** {raid['scheduled_time']}\n\n"
                        f"💬 Use o botão abaixo para entrar na raid!"
                    ),
                    color=Color.blue(),
                    timestamp=datetime.utcnow()
                )
                
                embed.set_footer(text=f"Raid ID: {raid_id}")
                
                view = View(timeout=3600)  # 1 hora
                accept_btn = Button(
                    style=ButtonStyle.green,
                    label="✅ Aceitar Convite",
                    custom_id=f"invite_accept_{raid_id}_{user.id}"
                )
                
                async def accept_callback(interaction: discord.Interaction):
                    if interaction.user.id != user.id:
                        return await interaction.response.send_message(
                            "❌ Este convite não é para você!",
                            ephemeral=True
                        )
                    
                    # Tentar adicionar à raid
                    success = await self.add_member_to_raid(raid_id, user.id)
                    
                    if success:
                        await interaction.response.send_message(
                            f"✅ Você aceitou o convite para **{boss['name']}**!",
                            ephemeral=True
                        )
                        
                        # Notificar na thread da raid
                        await self.send_to_raid_thread(
                            raid_id,
                            f"🎉 {user.mention} aceitou o convite e entrou na raid!"
                        )
                        
                        # Verificar se está completa
                        if len(raid['members']) >= raid['party_size']:
                            await self.handle_raid_filled(raid_id)
                            
                    else:
                        await interaction.response.send_message(
                            "❌ Não foi possível entrar na raid. Pode estar cheia ou cancelada.",
                            ephemeral=True
                        )
                
                accept_btn.callback = accept_callback
                view.add_item(accept_btn)
                
                await user.send(embed=embed, view=view)
                
                # Armazenar convite pendente
                if user.id not in self.pending_invites:
                    self.pending_invites[user.id] = {}
                self.pending_invites[user.id][raid_id] = {
                    'inviter_id': inviter.id,
                    'sent_at': datetime.utcnow()
                }
                
                return True
                
            except Exception as e:
                logger.error(f"Error sending raid invite to {user.id}: {e}")
                return False
        
        def format_duration(self, start: datetime, end: datetime) -> str:
            """Formata duração entre dois tempos"""
            duration = end - start
            total_seconds = int(duration.total_seconds())
            
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"

# ═══════════════════════════════════════════════════════════════════════════════════════
# SETUP DO COG
# ═══════════════════════════════════════════════════════════════════════════════════════

def setup(bot: commands.Bot):
    """Setup do cog"""
    bot.add_cog(RaidBuilderSystem(bot))
    logger.info("RaidBuilderSystem cog loaded successfully")