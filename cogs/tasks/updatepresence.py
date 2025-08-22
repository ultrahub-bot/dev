# cogs/tasks/updatepresence.py
import discord
from discord.ext import commands
import asyncio
from datetime import datetime

class UpdatePresence(commands.Cog):
    """Handles automated presence updates with rotation and error handling"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.presence_index = 0
        self.presence_rotation = [
            {
                'type': discord.ActivityType.watching,
                'name': "Hello, I'm {bot_name}!",
                'details': "Main System Online"
            },
            {
                'type': discord.ActivityType.listening,
                'name': "/help for commands",
                'details': "Available 24/7"
            },
            {
                'type': discord.ActivityType.playing,
                'name': "with {guild_count} servers",
                'details': "UltraHub Bot"
            }
        ]
        self.presence_task = None

    async def cog_load(self):
        """Start the presence task when cog is loaded"""
        self.presence_task = self.bot.loop.create_task(self.update_presence())
        print("✅ Presence update task started")

    async def cog_unload(self):
        """Ensure proper cleanup"""
        if self.presence_task:
            self.presence_task.cancel()
            try:
                await self.presence_task
            except asyncio.CancelledError:
                print("🛑 Presence task cancelled")
                pass

    async def update_presence(self):
        """Main presence update loop"""
        try:
            await self.bot.wait_until_ready()
            
            error_count = 0
            while not self.bot.is_closed():
                try:
                    current = self.presence_rotation[self.presence_index]
                    
                    # Format dynamic variables
                    formatted_name = current['name'].format(
                        bot_name=self.bot.user.name,
                        guild_count=len(self.bot.guilds)
                    )
                    activity = discord.Activity(
                        type=current['type'],
                        name=formatted_name,
                        details=f"{current['details']} | {datetime.now().strftime('%d/%m %H:%M')}"
                    )
                    
                    print(f"🔄 Updating presence to: {formatted_name}")
                    await self.bot.change_presence(activity=activity)
                    
                    # Rotate to next presence
                    self.presence_index = (self.presence_index + 1) % len(self.presence_rotation)
                    error_count = 0
                    await asyncio.sleep(30)  # Update every 30 seconds for testing
                    
                except discord.Forbidden as e:
                    if e.code == 50005:
                        print("⚠️ Presence update skipped (insufficient permissions)")
                        await asyncio.sleep(300)
                    else:
                        raise
                        
                except Exception as e:
                    error_count += 1
                    wait_time = min(10 * error_count, 300)
                    print(f"⚠️ Presence update failed (retry in {wait_time}s): {str(e)}")
                    await asyncio.sleep(wait_time)
                    
        except Exception as e:
            print(f"❌ Fatal error in presence task: {str(e)}")
            raise

def setup(bot: commands.Bot):
    """Cog setup function"""
    bot.add_cog(UpdatePresence(bot))
    #print("✅ Presence cog loaded")