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
from config import RAID_CHANNEL_ID, REQUIRED_VOICE_CHANNEL_ID

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes
#REQUIRED_VOICE_CHANNEL_ID = REQUIRED_VOICE_CHANNEL_ID

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
        """Handler para quando alguém sai de um canal de fila de raid"""
        if member.bot:
            return
        
        raid_id = self.voice_channel_raids.get(voice_channel.id)
        if not raid_id or raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        
        # Se a raid já foi concluída ou falhou, não mexer
        if raid['status'] in ['completed', 'failed']:
            return
        
        # Remover membro da raid se ele estava listado
        if member.id in raid['members']:
            await self.remove_member_from_raid(raid_id, member.id)

            # Se o membro era o líder → passar liderança
            if member.id == raid['leader_id']:
                if raid['members']:
                    new_leader = raid['members'][0]
                    raid['leader_id'] = new_leader
                    logger.info(f"Liderança da raid {raid_id} passada para {new_leader}")
                    await self.send_to_raid_thread(
                        raid_id,
                        f"👑 {member.mention} saiu da call. A liderança foi passada para <@{new_leader}>."
                    )
                else:
                    # Se não sobrou ninguém → cancelar raid
                    await self.cleanup_raid(raid_id)
                    return
            
            # Notificar apenas se a raid ainda está recrutando
            if raid['status'] == 'recruiting':
                try:
                    boss = db.get_boss(raid['boss_id'])
                    await member.send(
                        f"📤 Você saiu da fila para **{boss['name']}** ao deixar o canal de voz."
                    )
                except:
                    pass
        
        # Cancelar raid se não sobrou ninguém (thread + lista de membros)
        if not raid['members']:
            await self.send_to_raid_thread(
                raid_id,
                f"❌ Todos os membros saíram. A raid foi cancelada automaticamente."
            )
            await self.cleanup_raid(raid_id)
            return
        
        # Se o canal de voz ficou vazio → deletar e cancelar raid
        if not voice_channel.members:
            try:
                await voice_channel.delete(reason="Raid encerrada - canal vazio")
                logger.info(f"Canal {voice_channel.id} deletado por estar vazio (raid {raid_id})")
            except Exception as e:
                logger.error(f"Erro ao deletar canal {voice_channel.id}: {e}")
            await self.send_to_raid_thread(
                raid_id,
                f"❌ O canal de voz foi esvaziado. A raid foi cancelada automaticamente."
            )
            await self.cleanup_raid(raid_id)

    
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
        
        # CORREÇÃO: mudar status para ready_check
        raid['status'] = 'ready_check'
        raid['ready_check_started'] = True
        raid['ready_check_expires'] = datetime.utcnow() + timedelta(minutes=1)
        raid['confirmed_members'].clear()
        
        # Atualizar embed - isso faz os botões aparecerem
        await self.update_raid_embed(raid_id)
        
        # Notificar na thread da raid
        boss = db.get_boss(raid['boss_id'])
        mentions = []
        for user_id in raid['members']:
            user = self.bot.get_user(user_id)
            if user:
                mentions.append(user.mention)
        
        # No método start_auto_ready_check, atualize a mensagem:
        await self.send_to_raid_thread(
            raid_id,
            f"🎯 **READY CHECK AUTOMÁTICO!**\n"
            f"🎮 Boss: **{boss['name']}**\n"
            f"⏰ Vocês têm 1 minuto para confirmar presença!\n"
            f"📋 Use `/raid confirmar` nesta thread ou clique no botão abaixo!\n\n"
            f"{' '.join(mentions)}",
            mention_role=True,
            add_confirm_buttons=True  
        )


    # ═══════════════════════════════════════════════════════════════════════════════════════
    # COMANDO PRINCIPAL - RAID BUILDER
    # ═══════════════════════════════════════════════════════════════════════════════════════
    
    raid_group = SlashCommandGroup("raid", "Sistema de raids e matchmaking")
    
    @raid_group.command(name="criar", description="🏰 Inicia a seleção de bosses para iniciar a raid.")
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
        
        #embed.add_field(
        #    name="🌐 **PÚBLICO**",
        #    value="Crie uma raid aberta para todos\n"
        #        "• Qualquer um pode entrar\n"
        #        "• Ready check automático\n"
        #        "• Rápido e simples",
        #    inline=False
        #)
        
        embed.add_field(
            name="🌐 **PÚBLICO**",
            value="Crie uma fila por canal de voz\n"
                "• Canal específico para cada boss\n"
                "• Entre no canal = entre na fila\n"
                "• Automático e intuitivo",
            inline=False
        )
        
        #embed.add_field(
        #    name="🔒 **PRIVADO**",
        #    value="Crie uma raid personalizada\n"
        #        "• Convide jogadores específicos\n"
        #        "• Controle total sobre participantes\n"
        #        "• Tamanho de grupo customizável",
        #    inline=False
        #)

        embed.add_field(
            name="COMO PARTICIPAR",
            value="Entre no canal de voz\n"
                "• Selecione o boss que quer lutar\n"
                "• Você será transferido(a) para um novo canal\n"
                "• Basta chamar seus amigos para ele",
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
            label="🌐 Público",
            style=ButtonStyle.green,
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
        
        #view.add_item(public_btn)
        view.add_item(voice_queue_btn)
        #view.add_item(private_btn)
        
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
            'voice_queue': 'Raid Pública', #fila de voz
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
                value=str(boss['id'])  
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
        """Limpa completamente uma raid da memória e redireciona usuários IMEDIATAMENTE"""
        if raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        
        # Redirecionar todos os membros para o canal required
        required_channel = self.bot.get_channel(REQUIRED_VOICE_CHANNEL_ID)
        if required_channel:
            for user_id in raid['members']:
                try:
                    # Encontrar o membro em todas as guilds
                    for guild in self.bot.guilds:
                        member = guild.get_member(user_id)
                        if member and member.voice and member.voice.channel:
                            # Verificar se está em um canal de fila desta raid
                            if raid.get('is_voice_queue'):
                                voice_channel_id = self.voice_queue_channels.get(raid['boss_id'])
                                if voice_channel_id and member.voice.channel.id == voice_channel_id:
                                    await member.move_to(required_channel)
                                    logger.info(f"User {user_id} moved to required channel")
                            # Para raids não-voice-queue, mover se estiver em qualquer canal
                            elif not raid.get('is_voice_queue'):
                                await member.move_to(required_channel)
                                logger.info(f"User {user_id} moved to required channel")
                except Exception as e:
                    logger.error(f"Error moving user {user_id} to required channel: {e}")
        
        # Deletar canal de voz se for uma raid de voice queue
        if raid.get('is_voice_queue') and raid['boss_id'] in self.voice_queue_channels:
            voice_channel_id = self.voice_queue_channels[raid['boss_id']]
            voice_channel = self.bot.get_channel(voice_channel_id)
            if voice_channel:
                try:
                    await voice_channel.delete(reason=f"Raid {raid_id} cleanup - Cancelled")
                    logger.info(f"Voice channel {voice_channel_id} deleted for raid {raid_id}")
                except Exception as e:
                    logger.error(f"Erro ao deletar canal de voz durante cleanup: {e}")
            
            # Limpar associações
            self.voice_queue_channels.pop(raid['boss_id'], None)
            self.voice_channel_raids.pop(voice_channel_id, None)
        
        # Deletar mensagem original
        if raid_id in self.raid_messages:
            msg_data = self.raid_messages[raid_id]
            channel = self.bot.get_channel(msg_data['channel_id'])
            if channel:
                try:
                    message = await channel.fetch_message(msg_data['message_id'])
                    await message.delete()
                    logger.info(f"Message {msg_data['message_id']} deleted for raid {raid_id}")
                except Exception as e:
                    logger.error(f"Erro ao deletar mensagem da raid {raid_id}: {e}")
            self.raid_messages.pop(raid_id, None)
        
        # DELETAR THREAD
        if raid_id in self.raid_threads:
            thread_id = self.raid_threads[raid_id]
            thread = self.bot.get_channel(thread_id)
            if thread:
                try:
                    await thread.delete()
                    logger.info(f"Thread {thread_id} deletada para raid {raid_id}")
                except Exception as e:
                    logger.error(f"Erro ao deletar thread da raid {raid_id}: {e}")
            # Remover da lista de threads mesmo se não conseguir deletar
            self.raid_threads.pop(raid_id, None)
        
        # Limpar índices de usuários
        for user_id in raid['members']:
            if user_id in self.user_raids:
                self.user_raids[user_id].discard(raid_id)
                if not self.user_raids[user_id]:
                    del self.user_raids[user_id]
        
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

    async def handle_thread_confirm(self, interaction: discord.Interaction, raid_id: int):
        """Handler para confirmação via botão na thread"""
        await self.handle_confirm_ready(interaction, raid_id)

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
        """Versão corrigida do envio de embed de raid com menção de role"""
        try:
            boss = db.get_boss(raid_data['boss_id'])
            leader = self.bot.get_user(raid_data['leader_id'])
            
            if not boss or not leader:
                logger.error(f"Boss or leader not found for raid {raid_data['id']}")
                return
            
            embed = self.create_raid_embed(raid_data, boss, leader)
            view = self.create_raid_view(raid_data)
            
            # Mensagem com menção da role se configurada
            message_content = ""
            if boss.get('notify_role_id'):
                message_content = f"<@&{boss['notify_role_id']}> Nova raid criada!"
            
            message = await channel.send(content=message_content, embed=embed, view=view)
            
            # Criar thread para a raid (SEM auto_archive_duration para não arquivar)
            thread_name = f"🎯 {boss['name']} - {leader.display_name}"
            thread = await message.create_thread(
                name=thread_name[:100]
                # Removido auto_archive_duration para não arquivar automaticamente
            )
            
            # Salvar referências
            self.raid_messages[raid_data['id']] = {
                'message_id': message.id,
                'channel_id': channel.id
            }
            self.raid_threads[raid_data['id']] = thread.id
            
            # Enviar mensagem inicial na thread
            thread_message = f"🎯 **Raid criada por {leader.mention}**\n"
            thread_message += f"🏰 **{boss['name']}** (Lvl {boss['level']})\n"
            thread_message += f"🗺️ **Mapa:** {boss['map']}\n"
            thread_message += f"⚔️ **Dificuldade:** {boss['difficulty']}/5\n"
            thread_message += f"👥 **Tamanho:** {len(raid_data['members'])}/{raid_data['party_size']}\n"
            thread_message += f"📋 **Descrição:** {raid_data['description']}\n"
            thread_message += f"⏰ **Horário:** {raid_data['scheduled_time']}\n\n"
            thread_message += f"💬 **Comandos úteis nesta thread:**\n"
            thread_message += f"• `/raid confirmar` - Confirmar presença no ready check\n"
            thread_message += f"• `/raid status_check` - Ver status de confirmações\n"
            thread_message += f"• `/raid leave` - Sair da raid\n\n"
            thread_message += f"🎮 Entre na raid usando os botões na mensagem acima!"

            await thread.send(thread_message)
            
            return message
            
        except Exception as e:
            logger.error(f"Error sending raid embed: {e}")
            return None
    def create_raid_embed(self, raid_data: Dict, boss: Dict, leader: discord.User) -> Embed:
        """Versão corrigida da criação do embed"""
        color_map = {
            'recruiting': Color.blue(),
            'ready_check': Color.gold(),
            'in_progress': Color.green(),
            'completed': Color.green(),
            'failed': Color.red(),
            'cancelled': Color.dark_gray()
        }
        
        status_texts = {
            'recruiting': "🟢 **RECRUTANDO**",
            'ready_check': "🎯 **READY CHECK**",
            'in_progress': "⚔️ **EM ANDAMENTO**",
            'completed': "✅ **CONCLUÍDA**",
            'failed': "❌ **FALHOU**",
            'cancelled': "🚫 **CANCELADA**"
        }
        
        embed = Embed(
            title=f"🎯 {boss['name']}",
            description=raid_data['description'],
            color=color_map.get(raid_data['status'], Color.blue()),
            timestamp=datetime.utcnow()
        )
        
        # Informações básicas
        embed.add_field(
            name="📋 Informações",
            value=f"**Líder:** {leader.mention}\n"
                f"**Nível:** {boss['level']}\n"
                f"**Mapa:** {boss['map']}\n"
                f"**Dificuldade:** {boss['difficulty']}/5",
            inline=True
        )
        
        # Status e membros
        members_text = self.format_members_list(raid_data)
        embed.add_field(
            name=f"👥 Membros ({len(raid_data['members'])}/{raid_data['party_size']})",
            value=members_text,
            inline=True
        )
        
        # Status e horário
        embed.add_field(
            name="⏰ Status",
            value=f"{status_texts[raid_data['status']]}\n"
                f"**Horário:** {raid_data['scheduled_time']}",
            inline=False
        )
        
        # Footer com ID da raid
        embed.set_footer(text=f"Raid ID: {raid_data['id']} • Criada em")
        
        return embed

    def create_raid_view(self, raid_data: Dict) -> View:
        """Versão corrigida da criação da view com botões funcionais"""
        view = View(timeout=None)

        # Helper functions para criar callbacks (sem async)
        def create_join_callback(raid_id):
            async def callback(interaction: discord.Interaction):
                await self.handle_join_button(interaction, raid_id)
            return callback

        def create_invite_callback(raid_id):
            async def callback(interaction: discord.Interaction):
                await self.handle_invite_modal(interaction, raid_id)
            return callback

        def create_ready_callback(raid_id):
            async def callback(interaction: discord.Interaction):
                await self.handle_ready_check(interaction, raid_id)
            return callback

        def create_confirm_callback(raid_id):
            async def callback(interaction: discord.Interaction):
                await self.handle_confirm_ready(interaction, raid_id)
            return callback

        def create_cancel_ready_callback(raid_id):
            async def callback(interaction: discord.Interaction):
                await self.handle_cancel_ready(interaction, raid_id)
            return callback

        def create_cancel_raid_callback(raid_id):
            async def callback(interaction: discord.Interaction):
                await self.handle_cancel_raid(interaction, raid_id)
            return callback

        def create_finish_callback(raid_id):
            async def callback(interaction: discord.Interaction):
                if interaction.user.id != raid_data['leader_id']:
                    return await interaction.response.send_message(
                        "❌ Apenas o líder pode concluir a raid!",
                        ephemeral=True
                    )
                raid = self.active_raids.get(raid_id)
                if raid:
                    raid['status'] = 'completed'
                    raid['completed_at'] = datetime.utcnow()
                    await self.update_raid_embed(raid_id)
                    await self.cleanup_raid(raid_id)
                    await interaction.response.send_message("✅ Raid concluída!", ephemeral=True)
            return callback

        def create_leader_confirm_callback(raid_id):
            async def callback(interaction: discord.Interaction):
                await self.handle_leader_confirm_callback(interaction, raid_id)
            return callback

        def create_complete_callback(raid_id):
            async def callback(interaction: discord.Interaction):
                if interaction.user.id != raid_data['leader_id']:
                    return await interaction.response.send_message(
                        "❌ Apenas o líder pode concluir a raid!",
                        ephemeral=True
                    )
                raid = self.active_raids.get(raid_id)
                if raid:
                    raid['status'] = 'completed'
                    raid['completed_at'] = datetime.utcnow()
                    await self.update_raid_embed(raid_id)
                    await self.cleanup_raid(raid_id)
                    await interaction.response.send_message("✅ Raid concluída!", ephemeral=True)
            return callback

        def create_problem_callback(raid_id):
            async def callback(interaction: discord.Interaction):
                raid = self.active_raids.get(raid_id)
                if raid:
                    await self.send_to_raid_thread(
                        raid_id,
                        f"⚠️ {interaction.user.mention} reportou um problema na raid!\n"
                        f"👑 Líder: <@{raid['leader_id']}> - Por favor, verifique."
                    )
                    await interaction.response.send_message(
                        "✅ Problema reportado ao líder!",
                        ephemeral=True
                    )
            return callback

        # ──────────────── STATUS: RECRUTANDO ────────────────
        if raid_data['status'] == 'recruiting':
            # Botão Entrar
            join_btn = Button(
                style=ButtonStyle.green,
                label="🎮 Entrar",
                custom_id=f"raid_join_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
            )
            join_btn.callback = create_join_callback(raid_data['id'])
            view.add_item(join_btn)

            # Botão Convidar (apenas para raids não-voice-queue)
            if not raid_data.get('is_voice_queue', False):
                invite_btn = Button(
                    style=ButtonStyle.blurple,
                    label="📨 Convidar",
                    custom_id=f"raid_invite_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
                )
                invite_btn.callback = create_invite_callback(raid_data['id'])
                view.add_item(invite_btn)

            # Botão Ready Check
            ready_btn = Button(
                style=ButtonStyle.gray,
                label="✅ Ready Check",
                custom_id=f"raid_ready_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
            )
            ready_btn.callback = create_ready_callback(raid_data['id'])
            view.add_item(ready_btn)

        # ──────────────── STATUS: READY CHECK ────────────────
        elif raid_data['status'] == 'ready_check':
            # Botão Confirmar
            confirm_btn = Button(
                style=ButtonStyle.green,
                label="✅ Confirmar",
                custom_id=f"raid_confirm_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
            )
            confirm_btn.callback = create_confirm_callback(raid_data['id'])
            view.add_item(confirm_btn)

            # Botão Cancelar Ready Check (apenas líder)
            cancel_ready_btn = Button(
                style=ButtonStyle.red,
                label="❌ Cancelar Ready Check",
                custom_id=f"raid_cancel_ready_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
            )
            cancel_ready_btn.callback = create_cancel_ready_callback(raid_data['id'])
            view.add_item(cancel_ready_btn)

            # Botão Confirmar Todos (apenas líder)
            leader_confirm_btn = Button(
                label="👑 Confirmar Todos",
                style=ButtonStyle.gray,
                custom_id=f"raid_leader_confirm_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
            )
            leader_confirm_btn.callback = create_leader_confirm_callback(raid_data['id'])
            view.add_item(leader_confirm_btn)

            # Se todos confirmaram, adicionar botão Concluir
            if len(raid_data['confirmed_members']) == len(raid_data['members']):
                finish_btn = Button(
                    style=ButtonStyle.success,
                    label="🏆 Concluir Raid",
                    custom_id=f"raid_finish_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
                )
                finish_btn.callback = create_finish_callback(raid_data['id'])
                view.add_item(finish_btn)

        # ──────────────── STATUS: EM ANDAMENTO ────────────────
        elif raid_data['status'] == 'in_progress':
            # Botão para marcar como concluída
            complete_btn = Button(
                style=ButtonStyle.success,
                label="✅ Concluir Raid",
                custom_id=f"raid_complete_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
            )
            complete_btn.callback = create_complete_callback(raid_data['id'])
            view.add_item(complete_btn)
            
            # Botão para reportar problema
            problem_btn = Button(
                style=ButtonStyle.red,
                label="❌ Reportar Problema",
                custom_id=f"raid_problem_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
            )
            problem_btn.callback = create_problem_callback(raid_data['id'])
            view.add_item(problem_btn)
            
            # Botão Cancelar Raid (apenas líder)
            cancel_raid_btn = Button(
                style=ButtonStyle.danger,
                label="🚫 Cancelar Raid",
                custom_id=f"raid_cancel_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
            )
            cancel_raid_btn.callback = create_cancel_raid_callback(raid_data['id'])
            view.add_item(cancel_raid_btn)

        # ──────────────── BOTÃO CANCELAR RAID ────────────────
        # (aparece em ambos os status)
        if raid_data['status'] in ['recruiting', 'ready_check']:
            cancel_raid_btn = Button(
                style=ButtonStyle.danger,
                label="🚫 Cancelar Raid",
                custom_id=f"raid_cancel_{raid_data['id']}_{int(datetime.utcnow().timestamp())}"
            )
            cancel_raid_btn.callback = create_cancel_raid_callback(raid_data['id'])
            view.add_item(cancel_raid_btn)

        return view


    async def update_raid_embed(self, raid_id: int):
        """Atualiza a mensagem embed de uma raid existente - VERSÃO FINAL CORRIGIDA"""
        if raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        boss = db.get_boss(raid['boss_id'])
        leader = self.bot.get_user(raid['leader_id'])

        if not boss or not leader:
            return

        # Montar embed atualizado
        embed = Embed(
            title=f"🏰 Raid: {boss['name']}",
            description=raid['description'],
            color=Color.blue()
        )
        embed.add_field(name="👑 Líder", value=f"{leader.mention}", inline=False)
        embed.add_field(name="📊 Status", value=raid['status'], inline=True)
        embed.add_field(name="👥 Jogadores", value=f"{len(raid['members'])}/{raid['party_size']}", inline=True)

        # Lista de membros com destaque no líder
        member_lines = []
        for user_id in raid['members']:
            user = self.bot.get_user(user_id)
            if not user:
                continue
            if user_id == raid['leader_id']:
                member_lines.append(f"👑 {user.mention}")
            else:
                # Marcar se já confirmou
                if user_id in raid['confirmed_members']:
                    member_lines.append(f"✅ {user.mention}")
                else:
                    member_lines.append(f"❔ {user.mention}")

        if member_lines:
            embed.add_field(
                name="📋 Membros",
                value="\n".join(member_lines),
                inline=False
            )

        # Footer com tempo
        created_at = raid['created_at'].strftime("%d/%m %H:%M")
        embed.set_footer(text=f"Criado em {created_at}")

        # Atualizar mensagem original
        if raid_id in self.raid_messages:
            msg_data = self.raid_messages[raid_id]
            channel = self.bot.get_channel(msg_data['channel_id'])
            if channel:
                try:
                    message = await channel.fetch_message(msg_data['message_id'])
                    await message.edit(embed=embed, view=self.create_raid_view(raid))
                except Exception as e:
                    logger.error(f"Erro ao atualizar embed da raid {raid_id}: {e}")

    # ═══════════════════════════════════════════════════════════════════════════════════════
    # HANDLERS DE INTERAÇÃO
    # ═══════════════════════════════════════════════════════════════════════════════════════

    async def handle_join_button(self, interaction: discord.Interaction, raid_id: int):
        """Handler para botão Entrar - VERSÃO FINAL CORRIGIDA"""
        if raid_id not in self.active_raids:
            return await interaction.response.send_message("❌ Esta raid não existe mais.", ephemeral=True)

        raid = self.active_raids[raid_id]

        # Bloquear se raid já estiver cheia
        if len(raid['members']) >= raid['party_size']:
            return await interaction.response.send_message(
                "❌ Esta raid já está cheia!", ephemeral=True
            )

        # Bloquear se já está na raid
        if interaction.user.id in raid['members']:
            return await interaction.response.send_message(
                "⚠️ Você já está nesta raid.", ephemeral=True
            )

        # Adicionar membro
        await self.add_member_to_raid(raid_id, interaction.user.id)
        await self.update_raid_embed(raid_id)
        await interaction.response.send_message(
            f"✅ Você entrou na raid **{db.get_boss(raid['boss_id'])['name']}**!",
            ephemeral=True
        )

        # Se raid completou → iniciar ready check
        if len(raid['members']) >= raid['party_size']:
            await self.handle_raid_filled(raid_id)


    async def handle_join_raid(self, interaction: discord.Interaction, raid_id: int):
        if raid_id not in self.active_raids:
            return await interaction.response.send_message(
                "❌ Esta raid não existe mais!",
                ephemeral=True
            )

        raid = self.active_raids[raid_id]
        
        # Verificar se é uma raid de voice queue
        if not raid.get('is_voice_queue'):
            return await interaction.response.send_message(
                "❌ Esta raid não usa sistema de voz!",
                ephemeral=True
            )
        
        # Obter canal de voz da raid
        voice_channel_id = self.voice_queue_channels.get(raid['boss_id'])
        if not voice_channel_id:
            return await interaction.response.send_message(
                "❌ Canal de voz não encontrado para esta raid!",
                ephemeral=True
            )
        
        voice_channel = self.bot.get_channel(voice_channel_id)
        if not voice_channel:
            return await interaction.response.send_message(
                "❌ Canal de voz não disponível!",
                ephemeral=True
            )

        if interaction.user.id in raid['members']:
            return await interaction.response.send_message(
                "❌ Você já está na raid!",
                ephemeral=True
            )

        # Adicionar à raid
        raid['members'].append(interaction.user.id)
        await self.update_raid_embed(raid_id)

        # Mover para canal de voz
        if interaction.user.voice:
            try:
                await interaction.user.move_to(voice_channel)
                await interaction.response.send_message(
                    f"✅ Você entrou na raid e foi movido para {voice_channel.mention}!",
                    ephemeral=True
                )
            except Exception as e:
                logger.error(f"Error moving user to voice channel: {e}")
                await interaction.response.send_message(
                    "⚠️ Não consegui mover você, entre manualmente no canal de voz da raid.",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                f"🎮 Você entrou na raid! Entre no canal de voz {voice_channel.mention}.",
                ephemeral=True
            )
        
        # Verificar se a raid está cheia
        if len(raid['members']) >= raid['party_size']:
            await self.handle_raid_filled(raid_id)    

    async def handle_invite_modal(self, interaction: discord.Interaction, raid_id: int):
        """Abrir modal para convidar jogadores"""
        if raid_id not in self.active_raids:
            return await interaction.response.send_message(
                "❌ Esta raid não existe mais!",
                ephemeral=True
            )
        
        raid = self.active_raids[raid_id]
        
        # Verificar permissões
        if interaction.user.id != raid['leader_id']:
            return await interaction.response.send_message(
                "❌ Apenas o líder da raid pode convidar jogadores!",
                ephemeral=True
            )
        
        modal = InviteModal(raid_id, self)
        await interaction.response.send_modal(modal)

    async def handle_ready_check(self, interaction: discord.Interaction, raid_id: int):
        """Versão corrigida do ready check"""
        if raid_id not in self.active_raids:
            return await interaction.response.send_message(
                "❌ Esta raid não existe mais!",
                ephemeral=True
            )
        
        raid = self.active_raids[raid_id]
        
        # Verificar permissões
        if interaction.user.id != raid['leader_id']:
            return await interaction.response.send_message(
                "❌ Apenas o líder da raid pode iniciar o ready check!",
                ephemeral=True
            )
        
        # Verificar status
        if raid['status'] != 'recruiting':
            return await interaction.response.send_message(
                f"❌ Não é possível iniciar ready check no status atual: {raid['status']}",
                ephemeral=True
            )
        
        # Verificar se tem membros suficientes
        if len(raid['members']) < 2:  # Pelo menos 2 pessoas
            return await interaction.response.send_message(
                "❌ Precisa de pelo menos 2 jogadores para iniciar o ready check!",
                ephemeral=True
            )
        
        # Iniciar ready check
        raid['ready_check_started'] = True
        raid['ready_check_expires'] = datetime.utcnow() + timedelta(minutes=2)
        raid['confirmed_members'].clear()
        raid['status'] = 'ready_check'
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)
        
        # Notificar na thread
        boss = db.get_boss(raid['boss_id'])
        mentions = [f"<@{user_id}>" for user_id in raid['members']]
        
        await self.send_to_raid_thread(
            raid_id,
            f"🎯 **READY CHECK INICIADO!**\n"
            f"🎮 Boss: **{boss['name']}**\n"
            f"⏰ Vocês têm 2 minutos para confirmar presença!\n"
            f"📋 Use `/raid confirmar` nesta thread ou clique no botão abaixo!\n\n"
            f"{' '.join(mentions)}",
            mention_role=True,
            add_confirm_buttons=True  # ← NOVO PARÂMETRO
        )
        
        await interaction.response.send_message(
            "✅ Ready check iniciado! Os membros têm 2 minutos para confirmar.",
            ephemeral=True
        )

    async def handle_confirm_ready(self, interaction_or_ctx, raid_id: int):
        """Versão universal da confirmação de ready que funciona com Interaction ou Context"""
        if raid_id not in self.active_raids:
            if hasattr(interaction_or_ctx, 'response'):
                await interaction_or_ctx.response.send_message(
                    "❌ Esta raid não existe mais!",
                    ephemeral=True
                )
            else:
                await interaction_or_ctx.followup.send(
                    "❌ Esta raid não existe mais!",
                    ephemeral=True
                )
            return
        
        raid = self.active_raids[raid_id]
        
        # Verificar se está no ready check
        if not raid['ready_check_started']:
            if hasattr(interaction_or_ctx, 'response'):
                await interaction_or_ctx.response.send_message(
                    "❌ Não há ready check ativo para esta raid!",
                    ephemeral=True
                )
            else:
                await interaction_or_ctx.followup.send(
                    "❌ Não há ready check ativo para esta raid!",
                    ephemeral=True
                )
            return
        
        # Obter user_id dependendo do tipo de objeto
        if hasattr(interaction_or_ctx, 'user'):
            user_id = interaction_or_ctx.user.id
        else:
            user_id = interaction_or_ctx.author.id
        
        # Verificar se é membro da raid
        if user_id not in raid['members']:
            if hasattr(interaction_or_ctx, 'response'):
                await interaction_or_ctx.response.send_message(
                    "❌ Você não é membro desta raid!",
                    ephemeral=True
                )
            else:
                await interaction_or_ctx.followup.send(
                    "❌ Você não é membro desta raid!",
                    ephemeral=True
                )
            return
        
        # Verificar se já confirmou
        if user_id in raid['confirmed_members']:
            if hasattr(interaction_or_ctx, 'response'):
                await interaction_or_ctx.response.send_message(
                    "✅ Você já confirmou sua presença!",
                    ephemeral=True
                )
            else:
                await interaction_or_ctx.followup.send(
                    "✅ Você já confirmou sua presença!",
                    ephemeral=True
                )
            return
        
        # Confirmar presença
        raid['confirmed_members'].add(user_id)
        
        # Obter menção do usuário
        user = self.bot.get_user(user_id)
        user_mention = user.mention if user else f"<@{user_id}>"
        
        # Notificar na thread
        await self.send_to_raid_thread(
            raid_id,
            f"✅ {user_mention} confirmou presença!\n"
            f"📊 {len(raid['confirmed_members'])}/{len(raid['members'])} confirmados\n"
            f"💡 Use `/raid confirmar` se ainda não confirmou!",
            add_confirm_buttons=True
        )
        
        # Responder ao usuário
        if hasattr(interaction_or_ctx, 'response'):
            await interaction_or_ctx.response.send_message(
                "✅ Presença confirmada! Aguarde o início da raid.",
                ephemeral=True
            )
        else:
            await interaction_or_ctx.followup.send(
                "✅ Presença confirmada! Aguarde o início da raid.",
                ephemeral=True
            )
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)

        # Se todos confirmaram, atualizar embed
        # Dentro de handle_confirm_ready, após confirmar presença:
        if len(raid['confirmed_members']) == len(raid['members']):
            # Se todos confirmaram, iniciar raid automaticamente
            raid['status'] = 'in_progress'
            raid['started_at'] = datetime.utcnow()
            raid['ready_check_started'] = False
            raid['ready_check_expires'] = None
            
            # Notificar início automático
            boss = db.get_boss(raid['boss_id'])
            mentions = [f"<@{user_id}>" for user_id in raid['members']]
            
            await self.send_to_raid_thread(
                raid_id,
                f"🎉 **TODOS CONFIRMARAM!**\n"
                f"🚀 **RAID INICIADA AUTOMATICAMENTE!** - {boss['name']}\n"
                f"{' '.join(mentions)}\n"
                f"🎮 BOA SORTE! ⚔️"
            )
            
            # Atualizar embed para mostrar novo status
            await self.update_raid_embed(raid_id)

    async def handle_cancel_ready(self, interaction: discord.Interaction, raid_id: int):
        """Versão corrigida do cancelamento de ready"""
        if raid_id not in self.active_raids:
            return await interaction.response.send_message(
                "❌ Esta raid não existe mais!",
                ephemeral=True
            )
        
        raid = self.active_raids[raid_id]
        
        # Verificar permissões
        if interaction.user.id != raid['leader_id']:
            return await interaction.response.send_message(
                "❌ Apenas o líder da raid pode cancelar o ready check!",
                ephemeral=True
            )
        
        # Cancelar ready check
        raid['ready_check_started'] = False
        raid['ready_check_expires'] = None
        raid['confirmed_members'].clear()
        raid['status'] = 'recruiting'
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)
        
        # Notificar na thread
        await self.send_to_raid_thread(
            raid_id,
            f"🚫 Ready check cancelado por {interaction.user.mention}.\n"
            f"🔄 A raid voltou ao modo de recrutamento."
        )
        
        await interaction.response.send_message(
            "✅ Ready check cancelado. A raid voltou ao recrutamento.",
            ephemeral=True
        )

    async def handle_cancel_raid(self, interaction: discord.Interaction, raid_id: int):
        """Versão corrigida do cancelamento de raid - cancelamento imediato"""
        if raid_id not in self.active_raids:
            return await interaction.response.send_message(
                "❌ Esta raid não existe mais!",
                ephemeral=True
            )
        
        raid = self.active_raids[raid_id]
        
        # Verificar permissões
        if interaction.user.id != raid['leader_id']:
            return await interaction.response.send_message(
                "❌ Apenas o líder da raid pode cancelá-la!",
                ephemeral=True
            )
        
        # Cancelar raid
        raid['status'] = 'cancelled'
        
        # Notificar na thread
        boss = db.get_boss(raid['boss_id'])
        await self.send_to_raid_thread(
            raid_id,
            f"🚫 **RAID CANCELADA**\n"
            f"❌ {interaction.user.mention} cancelou a raid para **{boss['name']}**.\n"
            f"📋 Motivo: Interrupção manual."
        )
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)
        
        # Limpar IMEDIATAMENTE em vez de esperar
        await self.cleanup_raid(raid_id)
        
        await interaction.response.send_message(
            "✅ Raid cancelada com sucesso!",
            ephemeral=True
        )
    # ═══════════════════════════════════════════════════════════════════════════════════════
    # FUNÇÕES AUXILIARES
    # ═══════════════════════════════════════════════════════════════════════════════════════
    
    async def add_member_to_raid(self, raid_id: int, user_id: int):
        """Adiciona membro à raid e atualiza índices"""
        if raid_id not in self.active_raids:
            return False
        
        raid = self.active_raids[raid_id]
        
        # Adicionar à lista de membros
        if user_id not in raid['members']:
            raid['members'].append(user_id)
        
        # Atualizar índice de usuário
        if user_id not in self.user_raids:
            self.user_raids[user_id] = set()
        self.user_raids[user_id].add(raid_id)
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)
        
        return True
    
    async def remove_member_from_raid(self, raid_id: int, user_id: int):
        """Remove membro da raid e atualiza índices"""
        if raid_id not in self.active_raids:
            return False
        
        raid = self.active_raids[raid_id]
        
        # Remover da lista de membros
        if user_id in raid['members']:
            raid['members'].remove(user_id)
        
        # Remover de confirmed se estiver lá
        if user_id in raid['confirmed_members']:
            raid['confirmed_members'].discard(user_id)
        
        # Atualizar índice de usuário
        if user_id in self.user_raids:
            self.user_raids[user_id].discard(raid_id)
            if not self.user_raids[user_id]:
                del self.user_raids[user_id]
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)
        
        return True
    

    async def send_to_raid_thread(self, raid_id: int, message: str, mention_role: bool = False, add_confirm_buttons: bool = False):
        """Envia mensagem para a thread da raid com opção de botões de confirmação"""
        if raid_id not in self.raid_threads:
            return None
        
        try:
            thread = self.bot.get_channel(self.raid_threads[raid_id])
            if not thread:
                return None
            
            view = None
            if add_confirm_buttons:
                view = View(timeout=None)
                confirm_btn = Button(
                    style=ButtonStyle.green,
                    label="✅ Confirmar Presença",
                    custom_id=f"thread_confirm_{raid_id}"
                )
                confirm_btn.callback = lambda i: self.handle_thread_confirm(i, raid_id)
                view.add_item(confirm_btn)
            
            if mention_role:
                message = f"{message}"
            
            return await thread.send(message, view=view)
            
        except Exception as e:
            logger.error(f"Error sending to raid thread {raid_id}: {e}")
            return None

    def format_members_list(self, raid_data: Dict) -> str:
        """Formata lista de membros para o embed"""
        members_text = []
        
        for user_id in raid_data['members']:
            user = self.bot.get_user(user_id)
            display_name = user.display_name if user else f"User {user_id}"
            
            # Adicionar emoji de status
            status_emoji = "✅" if user_id in raid_data['confirmed_members'] else "⏳"
            
            # Adicionar coroa para líder
            if user_id == raid_data['leader_id']:
                display_name = f"👑 {display_name}"
            
            members_text.append(f"{status_emoji} {display_name}")
        
        return "\n".join(members_text) if members_text else "Nenhum membro ainda"
    
    async def send_raid_invite(self, raid_id: int, user: discord.User, inviter: discord.User) -> bool:
        """Envia convite de raid para um usuário"""
        if raid_id not in self.active_raids:
            return False
        
        raid = self.active_raids[raid_id]
        boss = db.get_boss(raid['boss_id'])
        
        try:
            embed = Embed(
                title=f"🎯 Convite de Raid - {boss['name']}",
                description=f"📋 **{inviter.display_name}** te convidou para uma raid!\n\n"
                          f"🗺️ **Mapa:** {boss['map']}\n"
                          f"⚔️ **Dificuldade:** {boss['difficulty']}/5\n"
                          f"👥 **Tamanho:** {len(raid['members'])}/{raid['party_size']}\n"
                          f"📝 **Descrição:** {raid['description']}\n"
                          f"⏰ **Horário:** {raid['scheduled_time']}",
                color=Color.gold()
            )
            
            view = View(timeout=3600)  # 1 hora de timeout
            
            accept_btn = Button(
                style=ButtonStyle.green,
                label="✅ Aceitar Convite",
                custom_id=f"invite_accept_{raid_id}_{user.id}"
            )
            
            decline_btn = Button(
                style=ButtonStyle.red,
                label="❌ Recusar",
                custom_id=f"invite_decline_{raid_id}_{user.id}"
            )
            
            async def accept_callback(interaction: discord.Interaction):
                if interaction.user.id != user.id:
                    return await interaction.response.send_message(
                        "❌ Este convite não é para você!",
                        ephemeral=True
                    )
                
                # Verificar se ainda pode entrar
                if raid_id not in self.active_raids:
                    return await interaction.response.send_message(
                        "❌ Esta raid não existe mais!",
                        ephemeral=True
                    )
                
                if raid['status'] != 'recruiting':
                    return await interaction.response.send_message(
                        f"❌ Esta raid não está mais recrutando! Status: {raid['status']}",
                        ephemeral=True
                    )
                
                if len(raid['members']) >= raid['party_size']:
                    return await interaction.response.send_message(
                        "❌ Esta raid já está cheia!",
                        ephemeral=True
                    )
                
                # Adicionar à raid
                await self.add_member_to_raid(raid_id, user.id)
                
                # Notificar na thread
                await self.send_to_raid_thread(
                    raid_id,
                    f"🎉 {user.mention} aceitou o convite e entrou na raid!\n"
                    f"👥 Agora temos {len(raid['members'])}/{raid['party_size']} jogadores."
                )
                
                await interaction.response.send_message(
                    f"✅ Você entrou na raid para **{boss['name']}**!\n"
                    f"👥 Posição: {len(raid['members'])}/{raid['party_size']}",
                    ephemeral=True
                )
                
                # Remover convite pendente
                if user.id in self.pending_invites:
                    if raid_id in self.pending_invites[user.id]:
                        del self.pending_invites[user.id][raid_id]
            
            async def decline_callback(interaction: discord.Interaction):
                if interaction.user.id != user.id:
                    return await interaction.response.send_message(
                        "❌ Este convite não é para você!",
                        ephemeral=True
                    )
                
                # Notificar o inviter
                try:
                    await inviter.send(
                        f"❌ {user.display_name} recusou seu convite para **{boss['name']}**."
                    )
                except:
                    pass
                
                # Remover convite pendente
                if user.id in self.pending_invites:
                    if raid_id in self.pending_invites[user.id]:
                        del self.pending_invites[user.id][raid_id]
                
                await interaction.response.send_message(
                    "❌ Convite recusado.",
                    ephemeral=True
                )
            
            accept_btn.callback = accept_callback
            decline_btn.callback = decline_callback
            
            view.add_item(accept_btn)
            view.add_item(decline_btn)
            
            # Salvar convite pendente
            if user.id not in self.pending_invites:
                self.pending_invites[user.id] = {}
            self.pending_invites[user.id][raid_id] = {
                'inviter_id': inviter.id,
                'sent_at': datetime.utcnow()
            }
            
            await user.send(embed=embed, view=view)
            return True
            
        except Exception as e:
            logger.error(f"Error sending raid invite: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════════════════════════════
    # TAREFAS EM BACKGROUND
    # ═══════════════════════════════════════════════════════════════════════════════════════
    @tasks.loop(seconds=10)
    async def thread_cleanup_task(self):
        """Limpeza periódica de threads órfãs"""
        try:
            channel = self.bot.get_channel(RAID_CHANNEL_ID)
            if not channel:
                return
            
            threads = channel.threads
            for thread in threads:
                # Verificar se é uma thread de raid (pelo nome) e se não está na lista ativa
                if thread.name.startswith("🎯"):
                    is_active = any(thread.id == tid for tid in self.raid_threads.values())
                    if not is_active:
                        try:
                            # Verificar se a thread está vazia ou muito antiga
                            messages = [message async for message in thread.history(limit=5)]
                            if len(messages) <= 1:  # Apenas mensagem inicial
                                await thread.delete()
                                logger.info(f"Thread órfã limpa: {thread.id}")
                        except Exception as e:
                            logger.error(f"Erro na limpeza de thread: {e}")
                            
        except Exception as e:
            logger.error(f"Error in thread cleanup task: {e}")    
    @tasks.loop(minutes=1)
    async def cleanup_task(self):
        """Limpeza periódica de raids expiradas"""
        try:
            current_time = datetime.utcnow()
            raids_to_cleanup = []
            
            for raid_id, raid in list(self.active_raids.items()):
                # Limpar raids canceladas/completadas após 5 minutos
                if raid['status'] in ['completed', 'failed', 'cancelled']:
                    if raid.get('completed_at') and (current_time - raid['completed_at']).total_seconds() > 300:
                        raids_to_cleanup.append(raid_id)
                
                # Limpar ready checks expirados
                elif raid['ready_check_started'] and raid['ready_check_expires']:
                    if current_time > raid['ready_check_expires']:
                        await self.handle_ready_check_expired(raid_id)
                
                # Limpar raids em recrutamento por muito tempo (2 horas)
                elif raid['status'] == 'recruiting':
                    if (current_time - raid['created_at']).total_seconds() > 7200:
                        raids_to_cleanup.append(raid_id)
            
            # Executar limpeza
            for raid_id in raids_to_cleanup:
                await self.cleanup_raid(raid_id)
                
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")

    @tasks.loop(seconds=30)
    async def voice_monitor(self):
        """Monitora canais de voz para manter sincronização"""
        try:
            for boss_id, voice_channel_id in list(self.voice_queue_channels.items()):
                voice_channel = self.bot.get_channel(voice_channel_id)
                if not voice_channel:
                    # Canal não existe mais, limpar
                    if boss_id in self.voice_queue_channels:
                        del self.voice_queue_channels[boss_id]
                    continue
                
                # Verificar se ainda está associado a uma raid ativa
                raid_id = self.voice_channel_raids.get(voice_channel_id)
                if not raid_id or raid_id not in self.active_raids:
                    # Raid não existe mais, deletar canal
                    try:
                        await voice_channel.delete(reason="Raid associated no longer exists")
                    except:
                        pass
                    if boss_id in self.voice_queue_channels:
                        del self.voice_queue_channels[boss_id]
                    if voice_channel_id in self.voice_channel_raids:
                        del self.voice_channel_raids[voice_channel_id]
                    continue
                
                raid = self.active_raids[raid_id]
                
                # Sincronizar membros do canal com a raid
                current_members = {m.id for m in voice_channel.members if not m.bot}
                raid_members = set(raid['members'])
                
                # Adicionar membros que estão no canal mas não na raid
                for user_id in current_members - raid_members:
                    if len(raid['members']) < raid['party_size']:
                        await self.add_member_to_raid(raid_id, user_id)
                
                # Remover membros que estão na raid mas não no canal
                for user_id in raid_members - current_members:
                    await self.remove_member_from_raid(raid_id, user_id)
                    
        except Exception as e:
            logger.error(f"Error in voice monitor task: {e}")

    @tasks.loop(seconds=10)
    async def ready_check_monitor(self):
        """Monitora ready checks expirados"""
        try:
            current_time = datetime.utcnow()
            
            for raid_id, raid in list(self.active_raids.items()):
                if raid['ready_check_started'] and raid['ready_check_expires']:
                    if current_time > raid['ready_check_expires']:
                        await self.handle_ready_check_expired(raid_id)
                        
        except Exception as e:
            logger.error(f"Error in ready check monitor: {e}")

    async def handle_ready_check_expired(self, raid_id: int):
        """Handler para quando o ready check expira"""
        if raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        boss = db.get_boss(raid['boss_id'])
        
        # Verificar quantos confirmaram
        confirmed_count = len(raid['confirmed_members'])
        total_members = len(raid['members'])
        
        if confirmed_count >= 4: #max(4, total_members * 0.7):  # Pelo menos 2 ou 70%
            # Iniciar raid
            await self.start_raid(raid_id)
        else:
            # Cancelar ready check
            raid['ready_check_started'] = False
            raid['ready_check_expires'] = None
            raid['confirmed_members'].clear()
            raid['status'] = 'recruiting'
            
            # Notificar na thread
            await self.send_to_raid_thread(
                raid_id,
                f"⏰ **READY CHECK EXPIRADO!**\n"
                f"❌ Não houve confirmações suficientes.\n"
                f"📊 {confirmed_count}/{total_members} confirmados\n"
                f"🔄 A raid voltou ao modo de recrutamento."
            )
            
            # Atualizar embed
            await self.update_raid_embed(raid_id)





    async def handle_leader_confirm_callback(self, interaction: discord.Interaction, raid_id: int):
        """Handler para quando o líder confirma todos os membros - VERSÃO CORRIGIDA"""
        if raid_id not in self.active_raids:
            return await interaction.response.send_message(
                "❌ Esta raid não existe mais!",
                ephemeral=True
            )
        
        raid = self.active_raids[raid_id]
        
        # Verificar permissões
        if interaction.user.id != raid['leader_id']:
            return await interaction.response.send_message(
                "❌ Apenas o líder da raid pode usar este botão!",
                ephemeral=True
            )
        
        # Confirmar todos os membros
        raid['confirmed_members'] = set(raid['members'])
        
        # MUDANÇA IMPORTANTE: Mudar status para in_progress automaticamente
        raid['status'] = 'in_progress'
        raid['started_at'] = datetime.utcnow()
        raid['ready_check_started'] = False
        raid['ready_check_expires'] = None
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)
        
        # Notificar na thread que a raid foi iniciada
        boss = db.get_boss(raid['boss_id'])
        mentions = [f"<@{user_id}>" for user_id in raid['members']]
        
        await self.send_to_raid_thread(
            raid_id,
            f"👑 **O líder confirmou a presença de todos!**\n"
            f"🚀 **RAID INICIADA!** - {boss['name']}\n"
            f"{' '.join(mentions)}\n"
            f"🎮 BOA SORTE! ⚔️"
        )
        
        await interaction.response.send_message(
            "✅ Todos confirmados e raid iniciada!",
            ephemeral=True
        )

    async def start_raid(self, raid_id: int):
        """Inicia a raid oficialmente"""
        if raid_id not in self.active_raids:
            return
        
        raid = self.active_raids[raid_id]
        boss = db.get_boss(raid['boss_id'])
        
        # Atualizar status
        raid['status'] = 'in_progress'
        raid['started_at'] = datetime.utcnow()
        raid['ready_check_started'] = False
        raid['ready_check_expires'] = None
        
        # Notificar na thread
        mentions = [f"<@{user_id}>" for user_id in raid['members']]
        
        await self.send_to_raid_thread(
            raid_id,
            f"🚀 **RAID INICIADA!**\n"
            f"🎯 Boss: **{boss['name']}**\n"
            f"👥 Grupo: {len(raid['members'])} jogadores\n"
            f"⏰ Iniciada em: <t:{int(raid['started_at'].timestamp())}:R>\n\n"
            f"🎮 **BOA SORTE, GUERREIROS!** ⚔️\n\n"
            f"{' '.join(mentions)}",
            mention_role=True
        )
        
        # Atualizar embed
        await self.update_raid_embed(raid_id)
        
        # Para raids de voice queue, mover para canal principal após conclusão
        if raid.get('is_voice_queue'):
            # Agendar retorno automático após tempo estimado
            asyncio.create_task(self.schedule_raid_completion(raid_id))

    async def schedule_raid_completion(self, raid_id: int):
        """Agenda conclusão automática para raids de voice queue"""
        try:
            # Tempo estimado baseado na dificuldade
            if raid_id not in self.active_raids:
                return
            
            raid = self.active_raids[raid_id]
            boss = db.get_boss(raid['boss_id'])
            
            # Tempo baseado na dificuldade (5-20 minutos)
            difficulty = boss.get('difficulty', 3)
            estimated_time = difficulty * 4  # 4 minutos por nível de dificuldade
            
            await asyncio.sleep(estimated_time * 60)  # Converter para segundos
            
            if raid_id in self.active_raids and raid['status'] == 'in_progress':
                # Marcar como completada automaticamente
                raid['status'] = 'completed'
                raid['completed_at'] = datetime.utcnow()
                
                # Notificar conclusão
                await self.send_to_raid_thread(
                    raid_id,
                    f"✅ **RAID CONCLUÍDA AUTOMATICAMENTE!**\n"
                    f"🎯 Esperamos que tenham derrotado **{boss['name']}** com sucesso!\n"
                    f"⏰ Duração: {estimated_time} minutos\n\n"
                    f"🏆 Parabéns pelo sucesso! 🎉"
                )
                
                # Atualizar embed
                await self.update_raid_embed(raid_id)
                
        except Exception as e:
            logger.error(f"Error in raid completion scheduling: {e}")

    # ═══════════════════════════════════════════════════════════════════════════════════════
    # COMANDOS ADICIONAIS
    # ═══════════════════════════════════════════════════════════════════════════════════════

    @raid_group.command(name="cleanup_threads", description="🧹 Limpar threads órfãs de raids")
    @commands.has_permissions(manage_messages=True)
    async def cleanup_orphaned_threads(self, ctx: discord.ApplicationContext):
        """Comando para limpar threads de raids que não existem mais"""
        await ctx.defer()
        
        channel = self.bot.get_channel(RAID_CHANNEL_ID)
        if not channel:
            return await ctx.followup.send("❌ Canal de raids não encontrado!")
        
        # Buscar todas as threads no canal de raids
        threads = channel.threads
        orphaned_count = 0
        
        for thread in threads:
            # Verificar se a thread pertence a uma raid ativa
            is_orphan = True
            for raid_id, thread_id in self.raid_threads.items():
                if thread.id == thread_id and raid_id in self.active_raids:
                    is_orphan = False
                    break
            
            # Se for órfã e começar com "🎯" (formato das threads de raid)
            if is_orphan and thread.name.startswith("🎯"):
                try:
                    await thread.delete()
                    orphaned_count += 1
                    logger.info(f"Thread órfã deletada: {thread.id} - {thread.name}")
                except Exception as e:
                    logger.error(f"Erro ao deletar thread órfã {thread.id}: {e}")
        
        await ctx.followup.send(f"✅ {orphaned_count} threads órfãs limpas!")
    
    @raid_group.command(name="status", description="📊 Ver status das raids ativas")
    async def raid_status(self, ctx: discord.ApplicationContext):
        """Mostra status de todas as raids ativas"""
        await ctx.defer()
        
        if not self.active_raids:
            return await ctx.followup.send("📭 Nenhuma raid ativa no momento!")
        
        # Separar raids por tipo
        public_raids = []
        voice_raids = []
        private_raids = []
        
        for raid in self.active_raids.values():
            if raid.get('is_voice_queue'):
                voice_raids.append(raid)
            elif raid.get('is_public'):
                public_raids.append(raid)
            else:
                private_raids.append(raid)
        
        embed = Embed(
            title="📊 STATUS DAS RAIDS ATIVAS",
            color=Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Raids públicas
        if public_raids:
            public_text = []
            for raid in public_raids[:5]:  # Limitar a 5
                boss = db.get_boss(raid['boss_id'])
                leader = self.bot.get_user(raid['leader_id'])
                if boss and leader:
                    public_text.append(
                        f"🎯 **{boss['name']}** - {len(raid['members'])}/{raid['party_size']} "
                        f"(Líder: {leader.display_name})"
                    )
            embed.add_field(
                name=f"🌐 RAID PÚBLICAS ({len(public_raids)})",
                value="\n".join(public_text) or "Nenhuma",
                inline=False
            )
        
        # Filas de voz
        if voice_raids:
            voice_text = []
            for raid in voice_raids[:5]:
                boss = db.get_boss(raid['boss_id'])
                leader = self.bot.get_user(raid['leader_id'])
                if boss and leader:
                    voice_channel_id = self.voice_queue_channels.get(raid['boss_id'])
                    voice_channel = self.bot.get_channel(voice_channel_id) if voice_channel_id else None
                    
                    voice_text.append(
                        f"🎤 **{boss['name']}** - {len(raid['members'])}/{raid['party_size']} "
                        f"(Canal: {voice_channel.mention if voice_channel else '❌'})"
                    )
            embed.add_field(
                name=f"🎤 FILAS DE VOZ ({len(voice_raids)})",
                value="\n".join(voice_text) or "Nenhuma",
                inline=False
            )
        
        # Raids privadas
        if private_raids:
            private_text = []
            for raid in private_raids[:3]:
                boss = db.get_boss(raid['boss_id'])
                leader = self.bot.get_user(raid['leader_id'])
                if boss and leader:
                    private_text.append(
                        f"🔒 **{boss['name']}** - {len(raid['members'])}/{raid['party_size']} "
                        f"(Líder: {leader.display_name})"
                    )
            embed.add_field(
                name=f"🔒 RAID PRIVADAS ({len(private_raids)})",
                value="\n".join(private_text) or "Nenhuma",
                inline=False
            )
        
        embed.set_footer(text=f"Total: {len(self.active_raids)} raids ativas")
        
        await ctx.followup.send(embed=embed)

    @raid_group.command(name="confirmar", description="✅ Confirma presença na raid")
    async def confirm_presence(
        self,
        ctx: discord.ApplicationContext,
        raid_id: Option(int, "ID da raid (opcional)", required=False)
    ):
        """Comando para confirmar presença diretamente"""
        await ctx.defer(ephemeral=True)
        
        # Se não fornecer raid_id, tentar encontrar automaticamente
        if not raid_id:
            user_raids = self.user_raids.get(ctx.author.id, set())
            active_ready_raids = [
                r_id for r_id in user_raids 
                if r_id in self.active_raids and 
                self.active_raids[r_id]['status'] == 'ready_check'
            ]
            
            if not active_ready_raids:
                return await ctx.followup.send(
                    "❌ Não encontrei nenhuma raid em ready check para você!",
                    ephemeral=True
                )
            
            # Usar a primeira raid encontrada
            raid_id = active_ready_raids[0]
        
        # Usar o handler existente de confirmação
        await self.handle_confirm_ready(ctx, raid_id)
    
    @raid_group.command(name="myraids", description="👤 Ver suas raids ativas")
    async def my_raids(self, ctx: discord.ApplicationContext):
        """Mostra raids ativas do usuário"""
        await ctx.defer(ephemeral=True)
        
        user_raids = self.user_raids.get(ctx.author.id, set())
        if not user_raids:
            return await ctx.followup.send(
                "📭 Você não está em nenhuma raid ativa!",
                ephemeral=True
            )
        
        embed = Embed(
            title=f"👤 SUAS RAIDS ATIVAS",
            color=Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        for raid_id in list(user_raids):
            if raid_id not in self.active_raids:
                continue
            
            raid = self.active_raids[raid_id]
            boss = db.get_boss(raid['boss_id'])
            
            if not boss:
                continue
            
            status_emoji = {
                'recruiting': '🟢',
                'ready_check': '🎯', 
                'in_progress': '⚔️',
                'completed': '✅',
                'failed': '❌',
                'cancelled': '🚫'
            }
            
            role = "👑 Líder" if raid['leader_id'] == ctx.author.id else "👥 Membro"
            
            embed.add_field(
                name=f"{status_emoji.get(raid['status'], '❓')} {boss['name']}",
                value=f"**Status:** {raid['status']}\n"
                    f"**Membros:** {len(raid['members'])}/{raid['party_size']}\n"
                    f"**Seu papel:** {role}\n"
                    f"**ID:** {raid_id}",
                inline=False
            )
        
        await ctx.followup.send(embed=embed, ephemeral=True)
    
    @raid_group.command(name="leave", description="🚪 Sair de uma raid")
    async def leave_raid(
        self,
        ctx: discord.ApplicationContext,
        raid_id: Option(int, "ID da raid que quer sair", required=False)
    ):
        """Sair de uma raid específica ou de todas"""
        await ctx.defer(ephemeral=True)
        
        user_raids = self.user_raids.get(ctx.author.id, set())
        if not user_raids:
            return await ctx.followup.send(
                "❌ Você não está em nenhuma raid!",
                ephemeral=True
            )
        
        if raid_id is None:
            # Sair de todas as raids
            left_count = 0
            for r_id in list(user_raids):
                if await self.remove_member_from_raid(r_id, ctx.author.id):
                    left_count += 1
            
            await ctx.followup.send(
                f"✅ Saiu de {left_count} raid(s)!",
                ephemeral=True
            )
        else:
            # Sair de raid específica
            if raid_id not in user_raids:
                return await ctx.followup.send(
                    f"❌ Você não está na raid {raid_id}!",
                    ephemeral=True
                )
            
            success = await self.remove_member_from_raid(raid_id, ctx.author.id)
            if success:
                await ctx.followup.send(
                    f"✅ Saiu da raid {raid_id}!",
                    ephemeral=True
                )
            else:
                await ctx.followup.send(
                    f"❌ Erro ao sair da raid {raid_id}!",
                    ephemeral=True
                )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Monitora entradas/saídas de canais de voz"""
        # 1. Mensagem ao entrar em canal de voz
        if before.channel != after.channel and after.channel:
            # Verificar se é um canal regular (não de fila)
            if after.channel.id != REQUIRED_VOICE_CHANNEL_ID and after.channel.id not in self.voice_channel_raids:
                # Procurar canal de texto com mesmo nome
                text_channel = discord.utils.get(
                    member.guild.text_channels,
                    category=after.channel.category,
                    name=after.channel.name
                )
                if text_channel:
                    await text_channel.send(
                        f"{member.mention} entrou no canal de voz **{after.channel.name}** 🎤\n"
                        "Qual boss vocês querem fazer? Use `/raid builder` para criar uma raid!"
                    )
        
        # 2. Monitor original para filas de voz (apenas se a raid ainda existir)
        if before.channel and before.channel.id in self.voice_channel_raids:
            raid_id = self.voice_channel_raids.get(before.channel.id)
            if raid_id and raid_id in self.active_raids:
                await self.handle_voice_leave(member, before.channel)
        
        if after.channel and after.channel.id in self.voice_channel_raids:
            raid_id = self.voice_channel_raids.get(after.channel.id)
            if raid_id and raid_id in self.active_raids:
                await self.handle_voice_join(member, after.channel)
        
        # 3. Redirecionar para canal required ao sair de canal de fila (apenas se a raid ainda existir)
        if (before.channel and before.channel.id in self.voice_channel_raids and 
            not after.channel and before.channel.id in self.voice_channel_raids):
            
            raid_id = self.voice_channel_raids.get(before.channel.id)
            if raid_id and raid_id in self.active_raids:
                required_channel = self.bot.get_channel(REQUIRED_VOICE_CHANNEL_ID)
                if required_channel:
                    try:
                        await member.move_to(required_channel)
                    except Exception as e:
                        logger.error(f"Error moving user to required channel: {e}")

def setup(bot: commands.Bot):
    bot.add_cog(RaidBuilderSystem(bot))