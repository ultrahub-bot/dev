import random
import discord
from discord.ext import commands
from discord.commands import Option
from discord.commands import slash_command


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @slash_command(guild_ids=[1361196873045643344])
    async def bola(self, ctx, pergunta: Option(str)):
        respostas = [
            "Sim", "Não", "Tente adivinhar...", "Muito duvidoso",
            "Claro", "Sem dúvida", "Muito provável", "Talvez seja possível",
            "Você será o juiz", "não... (╯°□°）╯︵ ┻━┻", "não... baka",
            "senpai, por favor não ;-;", "acho que...", "gg", 
            "Eu-\nnão sei o que dizer"
        ]

        resposta = random.choice(respostas)
        await ctx.respond(f"🎱 **Pergunta:** {pergunta}\n**Resposta:** {resposta}")
        
        
    @slash_command(guild_ids=[1361196873045643344])
    async def gostosa(self, ctx, user: Option(discord.Member)):    
        random.seed(user.id)
        r = random.randint(1, 100)
        hot = r / 1.17

        if hot > 75:
            emoji = "💞"
        elif hot > 50:
            emoji = "💖"
        elif hot > 25:
            emoji = "❤"
        else:
            emoji = "💔"    

        await ctx.respond(f"**{user.name}** é **{hot:.2f}%** gostosa {emoji}")            

def setup(bot):
    bot.add_cog(Fun(bot))