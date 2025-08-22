import discord
from discord.ext import commands
from discord.commands import Option, SlashCommandGroup
import os
import asyncio
import random
from typing import Dict, Optional, List


async def safe_respond(ctx, content=None, **kwargs):
    """Responde ao usuário com retry/backoff se cair em rate limit"""
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            return await ctx.respond(content, **kwargs)
        except discord.HTTPException as e:
            if e.status == 429 and attempt < max_attempts - 1:
                wait_time = (2 ** attempt) + random.random()
                await asyncio.sleep(wait_time)
                continue
            raise


class MusicPlayer(commands.Cog):
    """Robust music player with automatic file handling and connection management"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_clients: Dict[int, discord.VoiceClient] = {}
        self.play_queues: Dict[int, asyncio.Queue] = {}
        self.current_tasks: Dict[int, asyncio.Task] = {}

        # Path configuration
        self.assets_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../assets'))
        self.ffmpeg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../ffmpeg.exe'))

        # Ensure assets directory exists
        os.makedirs(self.assets_path, exist_ok=True)

        # Audio configuration
        self.FFMPEG_OPTIONS = {
            'executable': self.ffmpeg_path,
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -filter:a "volume=0.8"'
        }

        # State tracking
        self.loop_modes: Dict[int, bool] = {}  # guild_id: is_looping
        self.connection_locks: Dict[int, asyncio.Lock] = {}

    music = SlashCommandGroup("music", "Music playback commands")

    async def _get_audio_files(self) -> List[str]:
        """Get all supported audio files from assets folder"""
        supported_extensions = ('.mp3', '.wav', '.ogg', '.flac')
        try:
            return [
                f for f in os.listdir(self.assets_path)
                if os.path.isfile(os.path.join(self.assets_path, f)) and f.lower().endswith(supported_extensions)
            ]
        except Exception as e:
            print(f"Error reading audio files: {e}")
            return []

    async def _get_connection_lock(self, guild_id: int) -> asyncio.Lock:
        """Get or create a connection lock for the guild"""
        if guild_id not in self.connection_locks:
            self.connection_locks[guild_id] = asyncio.Lock()
        return self.connection_locks[guild_id]

    async def _connect_voice(self, ctx: discord.ApplicationContext) -> Optional[discord.VoiceClient]:
        """Handle voice connection with robust error handling"""
        if not ctx.author.voice:
            await safe_respond(ctx, "❌ You must be in a voice channel!", ephemeral=True)
            return None

        guild_id = ctx.guild.id
        lock = await self._get_connection_lock(guild_id)

        async with lock:
            try:
                if guild_id in self.voice_clients:
                    vc = self.voice_clients[guild_id]
                    if vc.is_connected() and vc.channel == ctx.author.voice.channel:
                        return vc
                    await self._disconnect_voice(guild_id)

                max_attempts = 3
                for attempt in range(max_attempts):
                    try:
                        await ctx.guild.change_voice_state(channel=None)
                        await asyncio.sleep(0.5)

                        voice_client = await ctx.author.voice.channel.connect(
                            timeout=30.0,
                            reconnect=False
                        )

                        if guild_id not in self.play_queues:
                            self.play_queues[guild_id] = asyncio.Queue()

                        if guild_id not in self.loop_modes:
                            self.loop_modes[guild_id] = True

                        return voice_client

                    except discord.errors.ClientException as e:
                        if "Already connected" in str(e):
                            if guild_id in self.voice_clients:
                                await self._disconnect_voice(guild_id)
                            continue
                        raise
                    except discord.errors.ConnectionClosed as e:
                        if attempt < max_attempts - 1:
                            wait_time = 1 + attempt
                            await asyncio.sleep(wait_time)
                            continue
                        raise
                    except Exception as e:
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(1)
                            continue
                        raise

            except discord.errors.ConnectionClosed as e:
                await safe_respond(ctx, f"❌ Failed to connect after {max_attempts} attempts (Error: {e.code})", ephemeral=True)
                return None
            except Exception as e:
                await safe_respond(ctx, f"❌ Connection error: {str(e)}", ephemeral=True)
                return None

    async def _disconnect_voice(self, guild_id: int):
        """Cleanly disconnect voice client"""
        try:
            if guild_id in self.current_tasks:
                task = self.current_tasks[guild_id]
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
                del self.current_tasks[guild_id]

            if guild_id in self.voice_clients:
                voice_client = self.voice_clients[guild_id]
                if voice_client.is_playing():
                    voice_client.stop()
                try:
                    await voice_client.disconnect()
                except Exception:
                    pass
                del self.voice_clients[guild_id]

            self.play_queues.pop(guild_id, None)
            self.loop_modes.pop(guild_id, None)

        except Exception as e:
            print(f"Error during disconnect: {e}")

    async def _player_loop(self, guild_id: int):
        """Main playback loop"""
        while True:
            try:
                voice_client = self.voice_clients.get(guild_id)
                if not voice_client or not voice_client.is_connected():
                    break

                audio_files = await self._get_audio_files()
                if not audio_files:
                    await asyncio.sleep(5)
                    continue

                if self.play_queues[guild_id].empty():
                    next_file = random.choice(audio_files)
                else:
                    next_file = await self.play_queues[guild_id].get()
                    if next_file is None:  # sinal de erro do after()
                        continue

                file_path = os.path.join(self.assets_path, next_file)
                if not os.path.exists(file_path):
                    print(f"Missing file: {file_path}")
                    continue

                try:
                    def _after_playback(error, gid=guild_id):
                        if error:
                            print(f"Playback error: {error}")
                        asyncio.run_coroutine_threadsafe(
                            self.play_queues[gid].put(None), self.bot.loop
                        )

                    voice_client.play(
                        discord.FFmpegPCMAudio(file_path, **self.FFMPEG_OPTIONS),
                        after=_after_playback
                    )

                    while voice_client.is_playing() or voice_client.is_paused():
                        await asyncio.sleep(0.1)

                    if self.loop_modes.get(guild_id, False):
                        await self.play_queues[guild_id].put(next_file)

                except Exception as e:
                    print(f"Playback error: {e}")
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Player loop error: {e}")
                await asyncio.sleep(5)

    @music.command(name="start", description="Start music playback")
    async def start_music(self, ctx: discord.ApplicationContext):
        """Start continuous music playback"""
        await ctx.defer()

        audio_files = await self._get_audio_files()
        if not audio_files:
            return await safe_respond(ctx, "❌ No audio files available in assets folder!")

        voice_client = await self._connect_voice(ctx)
        if not voice_client:
            return

        self.voice_clients[ctx.guild.id] = voice_client

        if ctx.guild.id not in self.current_tasks:
            self.current_tasks[ctx.guild.id] = asyncio.create_task(self._player_loop(ctx.guild.id))

        await safe_respond(ctx, "🎶 Started music playback! Looping through all available tracks.")

    @music.command(name="stop", description="Stop music playback")
    async def stop_music(self, ctx: discord.ApplicationContext):
        """Stop playback and disconnect"""
        if ctx.guild.id not in self.voice_clients:
            return await safe_respond(ctx, "❌ Not currently playing!", ephemeral=True)

        await self._disconnect_voice(ctx.guild.id)
        await safe_respond(ctx, "⏹ Stopped music playback.")

    @music.command(name="skip", description="Skip current track")
    async def skip_track(self, ctx: discord.ApplicationContext):
        """Skip the currently playing track"""
        if ctx.guild.id not in self.voice_clients:
            return await safe_respond(ctx, "❌ Not currently playing!", ephemeral=True)

        voice_client = self.voice_clients[ctx.guild.id]
        if voice_client.is_playing():
            voice_client.stop()
            await safe_respond(ctx, "⏭ Skipped current track.")
        else:
            await safe_respond(ctx, "❌ No track is currently playing!", ephemeral=True)

    @music.command(name="tracks", description="List available tracks")
    async def list_tracks(self, ctx: discord.ApplicationContext):
        """Show all available audio tracks"""
        audio_files = await self._get_audio_files()
        if not audio_files:
            return await safe_respond(ctx, "❌ No audio files found in assets folder!", ephemeral=True)

        embed = discord.Embed(
            title="🎵 Available Tracks",
            description=f"Found {len(audio_files)} tracks in assets folder",
            color=discord.Color.blurple()
        )

        for i in range(0, len(audio_files), 10):
            chunk = audio_files[i:i+10]
            embed.add_field(
                name=f"Tracks {i+1}-{i+len(chunk)}",
                value="\n".join(f"`{f}`" for f in chunk),
                inline=False
            )

        await safe_respond(ctx, embed=embed)

    @music.command(name="loop", description="Toggle loop mode")
    async def toggle_loop(self, ctx: discord.ApplicationContext):
        """Toggle continuous looping of tracks"""
        if ctx.guild.id not in self.loop_modes:
            return await safe_respond(ctx, "❌ Player not active!", ephemeral=True)

        self.loop_modes[ctx.guild.id] = not self.loop_modes[ctx.guild.id]
        mode = "ON" if self.loop_modes[ctx.guild.id] else "OFF"
        await safe_respond(ctx, f"🔁 Loop mode: {mode}")

    @music.command(name="fix", description="Reset voice connection (use if stuck)")
    async def fix_voice(self, ctx: discord.ApplicationContext):
        """Force-reset the bot's voice state"""
        await ctx.defer()

        if ctx.guild.id in self.voice_clients:
            await self._disconnect_voice(ctx.guild.id)

        await ctx.guild.change_voice_state(channel=None)
        await asyncio.sleep(1)
        await safe_respond(ctx, "✅ Voice connection reset. Try `/music start` again.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Auto-disconnect when alone in voice channel or bot is kicked"""
        if member.bot:
            return

        voice_client = self.voice_clients.get(member.guild.id)
        if (
            voice_client
            and voice_client.channel
            and len([m for m in voice_client.channel.members if not m.bot]) == 0
        ):
            await self._disconnect_voice(member.guild.id)

        if member.id == self.bot.user.id and after.channel is None:
            await self._disconnect_voice(member.guild.id)

    def cog_unload(self):
        """Clean up on cog unload"""
        async def _cleanup():
            for guild_id in list(self.voice_clients.keys()):
                await self._disconnect_voice(guild_id)
            for task in list(self.current_tasks.values()):
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        asyncio.create_task(_cleanup())


def setup(bot):
    bot.add_cog(MusicPlayer(bot))
