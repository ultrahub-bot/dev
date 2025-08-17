# Tasks
---

Destinado para *cogs* do tipo Tarefa, que irão se executar automaticamente no servidor em um certo período de tempo.

Um exemplo seria FEED, onde o robô ficaria aguardando receber um vídeo do Youtube ou de qualquer outro meio cadastrado e postar para um canal específico.

```python
# task_template.py
import discord
from discord.ext import commands
import asyncio
import aiohttp

# ============================
# DISCORD COG TASK TEMPLATE
# ============================

class TaskTemplate(commands.Cog):
    """
    Universal Discord Cog Template
    - Supports: Slash commands, groups, buttons, selects, embeds, threads, persistent views.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bg_task = self.bot.loop.create_task(self.background_task())


    # EXEMPLO - TAREFA EM SEGUNDO PLANO
 
    async def background_task(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            print("⏳ Background task running...")
            await asyncio.sleep(60)

def setup(bot):
    bot.add_cog(TaskTemplate(bot))
```