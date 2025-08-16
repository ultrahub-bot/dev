# cogs/Feeds/feeds.py
import discord
from discord.ext import commands, tasks
import discord.utils
from discord.commands import SlashCommandGroup, Option
from discord.ext.commands import cooldown, BucketType  
import aiohttp
import asyncio
import feedparser
from datetime import datetime, timedelta
import config
import random

class FeedMonitor(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_interval = 1800  # 30 minutos
        self.youtube_channels = config.load_feeds("youtube")
        self.twitch_channels = config.load_feeds("twitch")
        self.twitter_users = config.load_feeds("twitter")
        self.rss_feeds = config.load_feeds("rss")
        
        # Cache para dados do YouTube
        self.youtube_channel_cache = {}
        self.api_request_cache = {}
        
        # Inicia com a primeira chave
        self.current_api_key = random.choice(config.YOUTUBE_API_KEYS) if hasattr(config, 'YOUTUBE_API_KEYS') else config.YOUTUBE_API_KEY

    monitor = SlashCommandGroup("monitor", "Gerencia feeds do bot")

    def _save_feeds(self, platform, data):
        config.save_feeds(platform, data)

    # --------------------- AUXILIAR -------------------------#
    async def get_channel_id_from_url(self, url: str) -> str:
        if url in self.youtube_channels:
            return self.youtube_channels[url]
            
        if url.startswith("https://www.youtube.com/@"):
            username = url.split("@")[1]
            api_url = f"https://www.googleapis.com/youtube/v3/channels?part=id&forUsername={username}&key={self.current_api_key}"
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    data = await resp.json()
                    if data.get('items'):
                        return data['items'][0]['id']
        elif "channel/" in url:
            return url.split("channel/")[1]
        return url

    async def cached_api_request(self, session, url):
        if url in self.api_request_cache:
            cache_time = self.api_request_cache[url]['time']
            if datetime.now() - cache_time < timedelta(minutes=30):
                return self.api_request_cache[url]['data']
        
        async with session.get(url) as resp:
            data = await resp.json()
            self.api_request_cache[url] = {'data': data, 'time': datetime.now()}
            return data

    async def update_channel_cache(self):
        channel_ids = [await self.get_channel_id_from_url(url) for url in self.youtube_channels.keys()]
        valid_ids = [cid for cid in channel_ids if cid]
        
        if not valid_ids:
            return

        url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&id={','.join(valid_ids)}&key={self.current_api_key}"
        async with aiohttp.ClientSession() as session:
            data = await self.cached_api_request(session, url)
            
        for item in data.get('items', []):
            channel_id = item['id']
            self.youtube_channel_cache[channel_id] = {
                'title': item['snippet']['title'],
                'subs': int(item['statistics']['subscriberCount'])
            }



    @staticmethod
    async def get_monitored_feeds(ctx: discord.AutocompleteContext):
        cog = ctx.bot.get_cog('FeedMonitor')
        if not cog:
            return []
        
        platform = ctx.options['plataforma']
        feeds_map = {
            "youtube": cog.youtube_channels,
            "twitch": cog.twitch_channels,
            "twitter": cog.twitter_users,
            "rss": cog.rss_feeds
        }
        return list(feeds_map.get(platform, {}).keys())
    # ---------------------- YOUTUBE ----------------------
    async def youtube_check(self):
        try:
            await self.update_channel_cache()
                        
            valid_ids = []
            for url in self.youtube_channels.keys():
                cid = await self.get_channel_id_from_url(url)
                if cid:
                    valid_ids.append(cid)            
            #valid_ids = [cid for cid in (await self.get_channel_id_from_url(url) for url in self.youtube_channels.keys()) if cid]
            if not valid_ids:
                return

            async with aiohttp.ClientSession() as session:
                search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={','.join(valid_ids)}&maxResults=1&order=date&type=video&key={self.current_api_key}"
                data = await self.cached_api_request(session, search_url)

                for item in data.get('items', []):
                    channel_id = item['snippet']['channelId']
                    video_id = item['id']['videoId']
                    
                    # Encontrar URL correspondente
                    channel_url = next((url for url, cid in self.youtube_channels.items() if cid == channel_id), None)
                    if not channel_url or self.youtube_channels[channel_url] == video_id:
                        continue

                    # Obter dados do cache
                    channel_data = self.youtube_channel_cache.get(channel_id, {})
                    
                    embed = discord.Embed(
                        title=item['snippet']['title'],
                        url=f"https://youtu.be/{video_id}",
                        description=(item['snippet']['description'][:200] + '...') if len(item['snippet']['description']) > 200 else item['snippet']['description'],
                        color=discord.Color.red(),
                        timestamp=datetime.utcnow()
                    )
                    embed.set_author(
                        name=channel_data.get('title', 'Canal YouTube'),
                        url=f"https://www.youtube.com/channel/{channel_id}"
                    )
                    embed.set_image(url=item['snippet']['thumbnails']['high']['url'])
                    embed.set_footer(text=f"{channel_data.get('subs', 'N/A')} inscritos")

                    self.youtube_channels[channel_url] = video_id
                    self._save_feeds("youtube", self.youtube_channels)
                    await self.send_notification("YouTube", embed=embed)

        except Exception as e:
            if "quotaExceeded" in str(e):
                print("Cota excedida! Rotacionando chaves e aumentando intervalo.")
                self.current_api_key = random.choice(config.YOUTUBE_API_KEYS)
                self.monitor_loop.change_interval(seconds=3600)  # 1 hora
            else:
                print(f"Erro no YouTube: {e}")

    # ---------------------- TASKS ----------------------

    async def twitch_check(self):
        headers = {
            'Client-ID': config.TWITCH_CLIENT_ID,
            'Authorization': f'Bearer {config.TWITCH_OAUTH_TOKEN}'
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            for channel, last_stream in self.twitch_channels.items():
                async with session.get(f'https://api.twitch.tv/helix/users?login={channel}') as resp:
                    user_data = await resp.json()
                if not user_data.get('data'):
                    continue

                user = user_data['data'][0]
                user_id = user['id']
                display_name = user['display_name']
                profile_image = user['profile_image_url']

                async with session.get(f'https://api.twitch.tv/helix/streams?user_id={user_id}') as resp:
                    stream_data = await resp.json()

                if stream_data.get('data'):
                    stream = stream_data['data'][0]
                    stream_id = stream['id']
                    if stream_id != last_stream:
                        title = stream['title']
                        thumbnail = stream['thumbnail_url'].replace("{width}", "640").replace("{height}", "360")
                        url = f"https://twitch.tv/{channel}"

                        embed = discord.Embed(
                            title=title,
                            url=url,
                            color=discord.Color.purple(),
                            timestamp=datetime.utcnow()
                        )
                        embed.set_author(name=display_name, url=url, icon_url=profile_image)
                        embed.set_image(url=thumbnail)
                        embed.set_footer(text="Twitch")

                        self.twitch_channels[channel] = stream_id
                        self._save_feeds("twitch", self.twitch_channels)
                        await self.send_notification("Twitch", embed=embed)
                        
    async def twitter_check(self):
        headers = {'Authorization': f'Bearer {config.TWITTER_BEARER_TOKEN}'}
        async with aiohttp.ClientSession(headers=headers) as session:
            for username, last_tweet in self.twitter_users.items():
                url = f"https://api.twitter.com/2/tweets/search/recent?query=from:{username}&max_results=1&tweet.fields=created_at,text"
                async with session.get(url) as resp:
                    data = await resp.json()

                if 'data' in data and data['data']:
                    tweet = data['data'][0]
                    tweet_id = tweet['id']
                    tweet_text = tweet['text']
                    tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"

                    if tweet_id != last_tweet:
                        embed = discord.Embed(
                            title=f"Novo tweet de @{username}",
                            description=(tweet_text[:200] + '...') if len(tweet_text) > 200 else tweet_text,
                            url=tweet_url,
                            color=discord.Color.blue(),
                            timestamp=datetime.utcnow()
                        )
                        embed.set_footer(text="Twitter")

                        self.twitter_users[username] = tweet_id
                        self._save_feeds("twitter", self.twitter_users)
                        await self.send_notification("Twitter", embed=embed)
    async def rss_check(self):
        async with aiohttp.ClientSession() as session:
            for feed_url, last_entry in self.rss_feeds.items():
                try:
                    async with session.get(feed_url) as resp:
                        feed_data = await resp.text()
                        feed = feedparser.parse(feed_data)

                        if not feed.entries:
                            continue

                        latest_entry = feed.entries[0]
                        entry_id = latest_entry.get('id', latest_entry.link)
                        title = latest_entry.get('title', 'Nova publicação')
                        link = latest_entry.get('link')
                        summary = latest_entry.get('summary', '')

                        if entry_id != last_entry:
                            embed = discord.Embed(
                                title=title,
                                url=link,
                                description=(summary[:200] + '...') if len(summary) > 200 else summary,
                                color=discord.Color.gold(),
                                timestamp=datetime.utcnow()
                            )
                            embed.set_author(name=feed.feed.get('title', 'RSS'))
                            embed.set_footer(text="RSS")

                            self.rss_feeds[feed_url] = entry_id
                            self._save_feeds("rss", self.rss_feeds)
                            await self.send_notification("RSS", embed=embed)
                except Exception as e:
                    print(f"Erro ao verificar RSS {feed_url}: {e}")

    @monitor.command(name="adicionar", description="Adiciona um feed ao monitoramento")
    async def add_feed(
        self,
        ctx,
        plataforma: Option(str, "Plataforma (youtube, twitch, twitter, rss)", choices=["youtube", "twitch", "twitter", "rss"]),
        target: Option(str, "ID ou URL do canal/feed")
    ):
        plataformas = {
            "youtube": self.youtube_channels,
            "twitch": self.twitch_channels,
            "twitter": self.twitter_users,
            "rss": self.rss_feeds
        }

        plataformas[plataforma][target] = None
        self._save_feeds(plataforma, plataformas[plataforma])
        await ctx.respond(f"✅ {target} adicionado ao monitoramento de {plataforma.title()}!", ephemeral=True)


    # Modifique a opção target no comando remover para usar autocomplete
    @monitor.command(name="remover", description="Remove um feed do monitoramento")
    async def remove_feed(
        self,
        ctx,
        plataforma: Option(str, "Plataforma (youtube, twitch, twitter, rss)", choices=["youtube", "twitch", "twitter", "rss"]),
        target: Option(str, "Selecione o feed para remover", autocomplete=discord.utils.basic_autocomplete(get_monitored_feeds))

    ):
        plataformas = {
            "youtube": self.youtube_channels,
            "twitch": self.twitch_channels,
            "twitter": self.twitter_users,
            "rss": self.rss_feeds
        }

        if target in plataformas[plataforma]:
            del plataformas[plataforma][target]
            self._save_feeds(plataforma, plataformas[plataforma])
            await ctx.respond(f"✅ {target} removido do monitoramento de {plataforma.title()}!", ephemeral=True)
        else:
            await ctx.respond("❌ Feed não encontrado!", ephemeral=True)


    @monitor.command(name="testar", description="Força checagem dos feeds agora")
    async def testar(self, ctx):
        await self.youtube_check()
        await self.twitch_check()
        await self.twitter_check()
        await self.rss_check()
        await ctx.respond("✅ Checagem manual concluída!", ephemeral=True)

    @monitor.command(name="repostar", description="Reenvia o último conteúdo conhecido de cada feed")
    async def repostar(self, ctx):
        await ctx.defer()
        async with aiohttp.ClientSession() as session:
            # YouTube
            for channel_url, video_id in self.youtube_channels.items():
                if not video_id:
                    continue
                video_url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={config.YOUTUBE_API_KEY}"
                async with session.get(video_url) as resp:
                    data = await resp.json()
                if 'items' not in data or not data['items']:
                    continue
                snippet = data['items'][0]['snippet']
                title = snippet['title']
                desc = snippet['description']
                thumb = snippet['thumbnails']['high']['url']
                channel_title = snippet['channelTitle']
                embed = discord.Embed(
                    title=title,
                    url=f"https://youtu.be/{video_id}",
                    description=(desc[:200] + "...") if len(desc) > 200 else desc,
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                embed.set_author(name=channel_title)
                embed.set_image(url=thumb)
                embed.set_footer(text="YouTube (repostado)")
                await self.send_notification("YouTube", embed=embed)
                break  # apenas um

            # Twitch
            for channel, stream_id in self.twitch_channels.items():
                if not stream_id:
                    continue
                url = f"https://twitch.tv/{channel}"
                embed = discord.Embed(
                    title=f"{channel} pode estar ao vivo!",
                    url=url,
                    description="Repost de teste do último stream conhecido.",
                    color=discord.Color.purple(),
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text="Twitch (repostado)")
                await self.send_notification("Twitch", embed=embed)
                break

            # Twitter
            for username, tweet_id in self.twitter_users.items():
                if not tweet_id:
                    continue
                tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
                embed = discord.Embed(
                    title=f"Repost de @{username}",
                    description="Último tweet repostado.",
                    url=tweet_url,
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text="Twitter (repostado)")
                await self.send_notification("Twitter", embed=embed)
                break

            # RSS
            for feed_url, entry_id in self.rss_feeds.items():
                if not entry_id:
                    continue
                feed_data = await session.get(feed_url)
                text = await feed_data.text()
                import feedparser
                feed = feedparser.parse(text)
                if not feed.entries:
                    continue
                entry = feed.entries[0]
                embed = discord.Embed(
                    title=entry.title,
                    url=entry.link,
                    description=(entry.get("summary", "")[:200] + "...") if len(entry.get("summary", "")) > 200 else entry.get("summary", ""),
                    color=discord.Color.gold(),
                    timestamp=datetime.utcnow()
                )
                embed.set_author(name=feed.feed.get("title", "RSS"))
                embed.set_footer(text="RSS (repostado)")
                await self.send_notification("RSS", embed=embed)
                break

        await ctx.respond("✅ Últimos conteúdos repostados!", ephemeral=True)


    # ---------------------- NOTIFICAÇÃO ---------------------- #
    async def send_notification(self, plataforma: str, content: str = None, embed: discord.Embed = None):
        channel = self.bot.get_channel(config.NOTIFICATION_CHANNEL_ID)
        if channel:
            if embed:
                await channel.send(embed=embed)
            else:
                fallback_embed = discord.Embed(
                    title=f"Novo conteúdo na {plataforma}!",
                    description=content or "",
                    color=discord.Color.blurple(),
                    timestamp=datetime.utcnow()
                )
                await channel.send(embed=fallback_embed)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.monitor_loop.is_running():
            self.monitor_loop.start()
        print(f"✅ {self.__class__.__name__} carregado com sucesso!")

    @tasks.loop(seconds=600)
    async def monitor_loop(self):
        await self.youtube_check()
        await self.twitch_check()
        await self.twitter_check()
        await self.rss_check()

    @tasks.loop(seconds=1800)
    async def monitor_loop(self):
        await self.youtube_check()
        await self.twitch_check()
        await self.twitter_check()
        await self.rss_check()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.monitor_loop.is_running():
            self.monitor_loop.start()
        print(f"✅ {self.__class__.__name__} carregado!")


def setup(bot):
    bot.add_cog(FeedMonitor(bot))

    