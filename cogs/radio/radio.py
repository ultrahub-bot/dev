import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
from discord import Option, Embed
import os
import random
import asyncio
from collections import deque
import subprocess
import logging

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RadioSystem(commands.Cog):
    """Sistema de rádio para reprodução de músicas com crossfade"""
    
    radio_group = SlashCommandGroup("radio", "Comandos de controle do rádio")
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_channel_id = 1406201408868450407  # Substitua pelo ID do seu canal de voz
        self.voice_client = None
        self.radio_on = False
        self.playlist = deque()
        self.current_track = None
        self.volume = 0.5
        self.fade_duration = 3  # segundos para crossfade
        self.assets_path = os.path.join(os.path.dirname(__file__), "assets")
        
        # Configuração do FFmpeg
        self.ffmpeg_path = self.find_ffmpeg()
        if not self.ffmpeg_path:
            logger.error("FFmpeg não encontrado! A funcionalidade de áudio não estará disponível.")
        
        self.ffmpeg_options = {
            'options': '-vn',
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        }
        
        self.load_music_files()
        self.shuffle_playlist()
    
    def find_ffmpeg(self):
        """Tenta encontrar o executável do FFmpeg"""
        try:
            # Verifica se o ffmpeg está no PATH
            subprocess.run(["ffmpeg", "-version"], 
                         check=True, 
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE)
            return "ffmpeg"
        except:
            # Verifica se o ffmpeg.exe está na pasta local
            local_ffmpeg = os.path.join(os.path.dirname(__file__), "ffmpeg.exe")
            if os.path.exists(local_ffmpeg):
                return local_ffmpeg
            return None
    
    def load_music_files(self):
        """Carrega todos os arquivos de música da pasta assets"""
        try:
            if not os.path.exists(self.assets_path):
                os.makedirs(self.assets_path, exist_ok=True)
                logger.info(f"Pasta assets criada em: {self.assets_path}")
                self.music_files = []
                return
            
            self.music_files = [
                f for f in os.listdir(self.assets_path) 
                if f.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a', '.flac'))
            ]
            
            if not self.music_files:
                logger.warning("Nenhum arquivo de música encontrado na pasta assets")
            else:
                logger.info(f"Carregadas {len(self.music_files)} músicas")
                
        except Exception as e:
            logger.error(f"Erro ao carregar arquivos de música: {e}")
            self.music_files = []
    
    def shuffle_playlist(self):
        """Embaralha a playlist"""
        if self.music_files:
            self.playlist = deque(random.sample(self.music_files, len(self.music_files)))
            logger.info("Playlist embaralhada")
    
    async def ensure_voice_connection(self, ctx):
        """Garante que o bot está conectado ao canal de voz"""
        try:
            if not self.ffmpeg_path:
                await ctx.respond("❌ FFmpeg não está instalado. Instale o FFmpeg para usar o rádio.")
                return False
            
            channel = self.bot.get_channel(self.voice_channel_id)
            if not channel:
                await ctx.respond("❌ Canal de voz não encontrado!")
                return False
            
            if self.voice_client:
                if self.voice_client.channel.id == self.voice_channel_id:
                    return True
                await self.voice_client.move_to(channel)
            else:
                self.voice_client = await channel.connect()
            
            return True
        except Exception as e:
            logger.error(f"Erro na conexão de voz: {e}")
            await ctx.respond(f"❌ Erro ao conectar ao canal de voz: {e}")
            return False
    
    async def play_next(self, ctx=None):
        """Reproduz a próxima música da playlist"""
        try:
            if not self.radio_on:
                return
                
            if not self.playlist:
                self.shuffle_playlist()
                if not self.playlist:
                    if ctx:
                        await ctx.respond("❌ Nenhuma música disponível na playlist.")
                    self.radio_on = False
                    return
            
            self.current_track = self.playlist[0]
            source_path = os.path.join(self.assets_path, self.current_track)
            
            if not os.path.exists(source_path):
                logger.warning(f"Arquivo não encontrado: {self.current_track}")
                self.playlist.rotate(-1)
                await self.play_next(ctx)
                return
            
            try:
                source = discord.FFmpegPCMAudio(
                    executable=self.ffmpeg_path,
                    source=source_path,
                    **self.ffmpeg_options
                )
                source = discord.PCMVolumeTransformer(source, volume=self.volume)
                
                if self.voice_client.is_playing():
                    # Crossfade entre músicas
                    new_source = discord.PCMVolumeTransformer(
                        discord.FFmpegPCMAudio(
                            executable=self.ffmpeg_path,
                            source=source_path,
                            **self.ffmpeg_options
                        ),
                        volume=0.1
                    )
                    self.voice_client.play(new_source, after=self.after_play)
                    
                    # Efeito de fade in/out
                    for i in range(1, 11):
                        if not self.radio_on:
                            break
                        new_source.volume = min(self.volume * (i/10), self.volume)
                        await asyncio.sleep(self.fade_duration/10)
                else:
                    self.voice_client.play(source, after=self.after_play)
                
                track_name = os.path.splitext(self.current_track)[0]
                if ctx:
                    embed = Embed(
                        title="🎶 Tocando Agora",
                        description=track_name,
                        color=discord.Color.blue()
                    )
                    await ctx.respond(embed=embed)
                logger.info(f"Tocando: {track_name}")
                
            except Exception as e:
                logger.error(f"Erro na reprodução: {e}")
                if ctx:
                    await ctx.respond(f"❌ Erro ao reproduzir: {e}")
                self.playlist.rotate(-1)
                await self.play_next(ctx)
                
        except Exception as e:
            logger.error(f"Erro em play_next: {e}")
            if ctx:
                await ctx.respond(f"❌ Erro: {e}")
            self.radio_on = False
    
    def after_play(self, error):
        """Callback após terminar uma música"""
        if error:
            logger.error(f"Erro na reprodução: {error}")
        
        if self.radio_on and self.playlist and self.current_track == self.playlist[0]:
            self.playlist.rotate(-1)
            asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)
    
    @radio_group.command(name="on", description="Liga o rádio")
    async def radio_on_cmd(self, ctx):
        """Inicia o rádio"""
        if self.radio_on:
            await ctx.respond("✅ O rádio já está ligado!")
            return
        
        if not await self.ensure_voice_connection(ctx):
            return
        
        self.radio_on = True
        await ctx.respond("🔊 Ligando o rádio...")
        await self.play_next(ctx)
    
    @radio_group.command(name="off", description="Desliga o rádio")
    async def radio_off_cmd(self, ctx):
        """Desliga o rádio"""
        if not self.radio_on:
            await ctx.respond("✅ O rádio já está desligado!")
            return
        
        self.radio_on = False
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        
        await ctx.respond("🔇 Desligando o rádio...")
    
    @radio_group.command(name="next", description="Pula para a próxima música")
    async def radio_next(self, ctx):
        """Pula para a próxima música"""
        if not self.radio_on:
            await ctx.respond("❌ O rádio não está ligado!")
            return
        
        if not self.playlist:
            await ctx.respond("❌ Playlist vazia!")
            return
        
        if self.playlist and self.current_track == self.playlist[0]:
            self.playlist.rotate(-1)
        
        if self.voice_client.is_playing():
            self.voice_client.stop()
        
        await ctx.respond("⏭ Pulando para a próxima música...")
    
    @radio_group.command(name="previous", description="Volta para a música anterior")
    async def radio_previous(self, ctx):
        """Volta para a música anterior"""
        if not self.radio_on:
            await ctx.respond("❌ O rádio não está ligado!")
            return
        
        if len(self.playlist) < 2:
            await ctx.respond("❌ Não há músicas suficientes na playlist!")
            return
        
        self.playlist.rotate(1)
        self.playlist.rotate(1)
        
        if self.voice_client.is_playing():
            self.voice_client.stop()
        
        await ctx.respond("⏮ Voltando para a música anterior...")
    
    async def search_autocomplete(self, ctx: discord.AutocompleteContext):
        """Autocomplete para busca de músicas"""
        search_term = ctx.value.lower()
        return [f for f in self.music_files if search_term in f.lower()][:25]
    
    @radio_group.command(name="search", description="Busca uma música para tocar")
    async def radio_search(
        self, 
        ctx, 
        query: Option(str, "Termo de busca", autocomplete=search_autocomplete)
    ):
        """Busca e reproduz uma música específica"""
        if not self.radio_on:
            await ctx.respond("❌ O rádio não está ligado!")
            return
        
        matches = [f for f in self.music_files if query.lower() in f.lower()]
        
        if not matches:
            await ctx.respond(f"❌ Nenhuma música encontrada com '{query}'")
            return
        
        if len(matches) == 1:
            selected = matches[0]
            if selected in self.playlist:
                self.playlist.remove(selected)
            self.playlist.appendleft(selected)
            
            if self.voice_client.is_playing():
                self.voice_client.stop()
            
            await ctx.respond(f"🔍 Tocando: {os.path.splitext(selected)[0]}")
        else:
            view = discord.ui.View(timeout=30)
            select = discord.ui.Select(
                placeholder=f"Selecione uma música ({len(matches)} encontradas)",
                options=[
                    discord.SelectOption(label=os.path.splitext(f)[0][:100], value=f)
                    for f in matches[:25]
                ]
            )
            
            async def callback(interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("❌ Este menu não é para você!", ephemeral=True)
                    return
                
                selected = select.values[0]
                if selected in self.playlist:
                    self.playlist.remove(selected)
                self.playlist.appendleft(selected)
                
                if self.voice_client.is_playing():
                    self.voice_client.stop()
                
                await interaction.response.send_message(f"🔍 Tocando: {os.path.splitext(selected)[0]}")
                view.stop()
            
            select.callback = callback
            view.add_item(select)
            
            await ctx.respond(f"🔍 Resultados para '{query}':", view=view)

def setup(bot):
    bot.add_cog(RadioSystem(bot))