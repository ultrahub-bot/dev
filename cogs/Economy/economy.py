# cogs/Economy/economy.py
import discord
from discord.ext import commands
from discord.commands import Option, SlashCommandGroup
import json
import random
import os
from typing import Optional, Tuple, List, Dict, Union
import requests
from discord.ext.commands import BucketType, CommandOnCooldown
from discord import Webhook
import aiohttp

# Adicione no topo com outros imports


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BANK_FILE = "./data/economy/mainbank.json"
        self.SHOP_FILE = "./data/economy/shop.json"
        self.ensure_bank_file()
        self.mainshop = self.load_shop()
        with open(os.path.join(os.path.dirname(__file__), "beg.json"), "r", encoding="utf-8") as f:
            self.beg_messages = json.load(f)
        with open(os.path.join(os.path.dirname(__file__), "rob.json"), "r", encoding="utf-8") as f:
            self.rob_messages = json.load(f)

    # Cria o grupo de comandos de economia
    economy = SlashCommandGroup("economia", "Comandos relacionados ao sistema econômico")

    def ensure_bank_file(self):
        """Garante que o arquivo de banco e diretório existam"""
        os.makedirs(os.path.dirname(self.BANK_FILE), exist_ok=True)
        if not os.path.exists(self.BANK_FILE):
            with open(self.BANK_FILE, 'w') as f:
                json.dump({}, f, indent=4)

    def load_shop(self):
        if not os.path.exists(self.SHOP_FILE):
            print(f"Arquivo {self.SHOP_FILE} não encontrado. Criando um arquivo de loja vazio.")
            with open(self.SHOP_FILE, "w") as f:
                json.dump([], f, indent=4)
            return []
        with open(self.SHOP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # ============= COMANDOS PRINCIPAIS =============
    
    @economy.command(name="saldo", description="Mostra seu saldo")
    async def balance(self, ctx):
        """Mostra o saldo da carteira e banco"""
        user = ctx.author
        await self.open_account(user)
        
        users = await self.get_bank_data()
        wallet = users[str(user.id)]["wallet"]
        bank = users[str(user.id)]["bank"]
        
        embed = discord.Embed(
            title=f'Saldo de {user.display_name}',
            color=discord.Color.gold()
        )
        embed.add_field(name="💵 Carteira", value=f"`{wallet} 🪙`")
        embed.add_field(name="🏦 Banco", value=f"`{bank} 🪙`")
        embed.set_thumbnail(url=user.display_avatar.url)
        
        await ctx.respond(embed=embed)

    @economy.command(name="mendigar", description="Pede moedas aleatórias")
    @commands.cooldown(1, 30, BucketType.user)
    async def beg(self, ctx):
        user = ctx.author
        await self.open_account(user)
        
        earnings = random.randint(10, 100)
        await self.update_bank(user, earnings)

        # Escolher template e formatar
        template = random.choice(self.beg_messages)
        msg = template.format(user=user.mention, amount=earnings)
        await ctx.respond(msg)


    @economy.command(name="sacar", description="Saca dinheiro do banco")
    async def withdraw(
        self, 
        ctx,
        amount: Option(str, "Quantidade para sacar (ou 'all')", required=True)
    ):
        """Saca dinheiro do banco"""
        user = ctx.author
        await self.open_account(user)
        
        users = await self.get_bank_data()
        bank_amt = users[str(user.id)]["bank"]
        
        if amount.lower() == "all":
            amount = bank_amt
        else:
            try:
                amount = int(amount)
            except ValueError:
                return await ctx.respond("Por favor insira um número válido ou 'all'")
        
        if amount > bank_amt:
            return await ctx.respond("Você não tem tanto dinheiro no banco!")
        if amount < 0:
            return await ctx.respond("Valor deve ser positivo!")
            
        await self.update_bank(user, amount)
        await self.update_bank(user, -amount, "bank")
        await ctx.respond(f"💵 {user.mention} sacou `{amount} 🪙` do banco!")

    @economy.command(name="depositar", description="Deposita dinheiro no banco")
    async def deposit(
        self, 
        ctx,
        amount: Option(str, "Quantidade para depositar (ou 'all')", required=True)
    ):
        """Deposita dinheiro no banco"""
        user = ctx.author
        await self.open_account(user)
        
        users = await self.get_bank_data()
        wallet_amt = users[str(user.id)]["wallet"]
        
        if amount.lower() == "all":
            amount = wallet_amt
        else:
            try:
                amount = int(amount)
            except ValueError:
                return await ctx.respond("Por favor insira um número válido ou 'all'")
        
        if amount > wallet_amt:
            return await ctx.respond("Você não tem tanto dinheiro na carteira!")
        if amount < 0:
            return await ctx.respond("Valor deve ser positivo!")
            
        await self.update_bank(user, -amount)
        await self.update_bank(user, amount, "bank")
        await ctx.respond(f"🏦 {user.mention} depositou `{amount} 🪙` no banco!")

    @economy.command(name="enviar", description="Envia dinheiro para outro usuário")
    async def send(
        self,
        ctx,
        member: Option(discord.Member, "Usuário para enviar", required=True),
        amount: Option(int, "Quantidade para enviar", min_value=1, required=True)
    ):
        """Envia dinheiro para outro usuário"""
        sender = ctx.author
        await self.open_account(sender)
        await self.open_account(member)
        
        users = await self.get_bank_data()
        
        if users[str(sender.id)]["wallet"] < amount:
            return await ctx.respond("Você não tem dinheiro suficiente!")
            
        await self.update_bank(sender, -amount)
        await self.update_bank(member, amount)
        await ctx.respond(f"💸 {sender.mention} enviou `{amount} 🪙` para {member.mention}!")

    @economy.command(name="roubar", description="Tenta roubar dinheiro de outro usuário")
    @commands.cooldown(1, 30, BucketType.user)
    async def rob(self, ctx, member: Option(discord.Member, "Usuário para roubar", required=True)):
        thief = ctx.author
        victim = member

        if thief == victim:
            return await ctx.respond("Você não pode roubar a si mesmo!")
        await self.open_account(thief)
        await self.open_account(victim)

        users = await self.get_bank_data()
        victim_bal = users[str(victim.id)]["wallet"]
        if victim_bal < 100:
            return await ctx.respond("Vítima é muito pobre para valer o roubo!")

        # Verifica se a vítima tem o item "Amulet of Thorns"
        victim_bag = users[str(victim.id)].get("bag", [])
        if any(item["item"].lower() == "amulet of thorns" for item in victim_bag):
            fine = random.randint(100, 300)
            await self.update_bank(thief, -fine)

            return await ctx.respond(
                f"🌵 {victim.mention} estava usando um **Amulet of Thorns**! "
                f"{thief.mention} tentou roubar e levou uma ferroada mágica, perdendo `{fine} 🪙`."
            )

        success = random.random() < 0.4  # 40% de chance
        if success:
            stolen = min(random.randint(1, victim_bal), victim_bal)
            await self.update_bank(thief, stolen)
            await self.update_bank(victim, -stolen)

            template = random.choice(self.rob_messages["success"])
            msg = template.format(thief=thief.mention, victim=victim.mention, amount=stolen)
            return await ctx.respond(msg)

        else:
            fine = random.randint(50, 200)
            await self.update_bank(thief, -fine)

            template = random.choice(self.rob_messages["failure"])
            msg = template.format(thief=thief.mention, victim=victim.mention, fine=fine)
            return await ctx.respond(msg)

    @economy.command(name="slots", description="Joga nos slots (apostas)")
    @commands.cooldown(1, 20, BucketType.user)  # 1 vez a cada 20 segundos
    async def slots(
        self,
        ctx,
        amount: Option(int, "Quantidade para apostar", min_value=1, required=True)
    ):
        """Joga nos slots (apostas)"""
        user = ctx.author
        await self.open_account(user)
        
        users = await self.get_bank_data()
        
        if users[str(user.id)]["wallet"] < amount:
            return await ctx.respond("Dinheiro insuficiente!")
            
        emojis = "🍎🍊🍇🍒🍋🍉🍓🍍"
        slots = [random.choice(emojis) for _ in range(3)]
        
        await ctx.respond(f"🎰 {' | '.join(slots)} 🎰")
        
        if slots[0] == slots[1] == slots[2]:
            win = amount * 5
            await self.update_bank(user, win)
            await ctx.respond(f"🎉 JACKPOT! Você ganhou {win} 🪙!")
        elif slots[0] == slots[1] or slots[1] == slots[2]:
            win = amount * 2
            await self.update_bank(user, win)
            await ctx.respond(f"✨ Você ganhou {win} 🪙!")
        else:
            await self.update_bank(user, -amount)
            await ctx.respond(f"😢 Você perdeu {amount} 🪙...")

    @economy.command(name="loja", description="Mostra os itens disponíveis na loja")
    async def shop(self, ctx: discord.ApplicationContext):
        """Mostra a loja de itens com embeds ricos"""
        try:
            await ctx.defer()
            
            embed = discord.Embed(
                title="🛒 Loja de Itens",
                description="Use `/economia comprar [item]` para adquirir os produtos",
                color=discord.Color.blue()
            )
            
            for item in self.mainshop:
                embed.add_field(
                    name=f"{item['name']} - {item['price']} 🪙",
                    value=item['description'],
                    inline=False
                )
            
            embed.set_footer(text=f"Pedido por {ctx.author.display_name}")
            
            await ctx.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Erro no comando shop: {str(e)}")
            try:
                await ctx.followup.send("❌ Ocorreu um erro ao mostrar a loja.", ephemeral=True)
            except:
                pass

    @commands.slash_command(name="comprar", description="Compra itens da loja")
    async def buy(
        self,
        ctx,
        item: Option(str, "Item para comprar", required=True),
        amount: Option(int, "Quantidade", default=1, min_value=1)
    ):
        user = ctx.author
        await self.open_account(user)
        
        item = item.lower()
        shop_item = next(
            (i for i in self.mainshop if i['name'].lower() == item), 
            None
        )

        if not shop_item:
            return await ctx.respond("Item não encontrado na loja!")

        total_cost = shop_item['price'] * amount

        users = await self.get_bank_data()
        if users[str(user.id)]["wallet"] < total_cost:
            return await ctx.respond("Dinheiro insuficiente!")

        # Verificação de requisitos
        missing = []

        ccid = users[str(user.id)].get("ccid")
        inventory = []
        badges = []

        # Requisições APENAS se necessário
        if ccid:
            if shop_item.get("aqwItemRequired"):
                inventory = requests.get(f"https://account.aq.com/CharPage/Inventory?ccid={ccid}").json()
            if shop_item.get("aqwBadgeRequired"):
                badges = requests.get(f"https://account.aq.com/CharPage/Badges?ccid={ccid}").json()

        # Verificar roles exigidas
        for role_id in shop_item.get("roleRequired", []):
            role = ctx.guild.get_role(int(role_id))
            if role and role not in user.roles:
                missing.append(f"📛 {role.name}")

        # Verificar itens do AQW
        for aqw_item in shop_item.get("aqwItemRequired", []):
            found = [i for i in inventory if aqw_item.lower() in i["strName"].lower()]
            total = sum(i["intCount"] for i in found)
            if total == 0:
                missing.append(f"🪙 {aqw_item}")

        # Verificar badges do AQW
        for badge_id in shop_item.get("aqwBadgeRequired", []):
            if not any(b["badgeID"] == badge_id for b in badges):
                missing.append(f"🎖️ Badge ID {badge_id} não encontrada")

        if missing:
            return await ctx.respond(
                f"❌ Você não pode comprar este item. Faltam os seguintes requisitos:\n" +
                "\n".join(missing)
            )

        # Atualizar carteira
        await self.update_bank(user, -total_cost)
        users = await self.get_bank_data()
        bag = users[str(user.id)].get("bag", [])

        existing_item = next(
            (i for i in bag if i['item'].lower() == item), 
            None
        )

        if existing_item:
            existing_item['amount'] += amount
        else:
            bag.append({"item": shop_item['name'], "amount": amount})

        users[str(user.id)]["bag"] = bag
        await self.save_bank_data(users)

        # Aplicar/Remover cargos
        roles_to_add = [ctx.guild.get_role(int(rid)) for rid in shop_item.get("roleGive", [])]
        roles_to_remove = [ctx.guild.get_role(int(rid)) for rid in shop_item.get("roleWithdraw", [])]

        if roles_to_add:
            await user.add_roles(*[r for r in roles_to_add if r])
        if roles_to_remove:
            await user.remove_roles(*[r for r in roles_to_remove if r])

        await ctx.respond(
            f"✅ {user.mention} comprou {amount}x **{shop_item['name']}** por {total_cost} 🪙!"
        )

    @economy.command(name="vender", description="Vende itens do inventário")
    async def sell(
        self,
        ctx,
        item: Option(str, "Item para vender", required=True),
        amount: Option(int, "Quantidade", default=1, min_value=1)
    ):
        """Vende itens do inventário"""
        user = ctx.author
        await self.open_account(user)
        
        item = item.lower()
        shop_item = next(
            (i for i in self.mainshop if i['name'].lower() == item), 
            None
        )
        
        if not shop_item:
            return await ctx.respond("Item não pode ser vendido na loja!")
            
        users = await self.get_bank_data()
        bag = users[str(user.id)].get("bag", [])
        
        existing_item = next(
            (i for i in bag if i['item'].lower() == item), 
            None
        )
        
        if not existing_item or existing_item['amount'] < amount:
            return await ctx.respond(f"Você não tem {amount}x {item} no inventário!")
            
        sell_price = int(shop_item['price'] * 0.8)
        total = sell_price * amount
        
        existing_item['amount'] -= amount
        if existing_item['amount'] <= 0:
            bag.remove(existing_item)
            
        users[str(user.id)]["bag"] = bag
        await self.save_bank_data(users)
        await self.update_bank(user, total)
        
        await ctx.respond(
            f"💰 {user.mention} vendeu {amount}x {shop_item['name']} por {total} 🪙!"
        )

    @economy.command(name="inventario", description="Mostra seu inventário")
    async def bag(self, ctx):
        """Mostra seu inventário"""
        user = ctx.author
        await self.open_account(user)
        
        users = await self.get_bank_data()
        bag = users[str(user.id)].get("bag", [])
        
        if not bag:
            return await ctx.respond("Seu inventário está vazio!")
            
        embed = discord.Embed(
            title=f"🎒 Inventário de {user.display_name}",
            color=discord.Color.green()
        )
        
        for item in bag:
            embed.add_field(
                name=item['item'],
                value=f"Quantidade: {item['amount']}",
                inline=False
            )
            
        await ctx.respond(embed=embed)

    @economy.command(name="ricos", description="Mostra os usuários mais ricos")
    async def richest(
        self,
        ctx,
        limit: Option(int, "Número de usuários para mostrar", default=10, min_value=1, max_value=25)
    ):
        """Mostra os usuários mais ricos"""
        users = await self.get_bank_data()
        rankings = []
        
        for user_id, data in users.items():
            try:
                user = await self.bot.fetch_user(int(user_id))
                total = data['wallet'] + data['bank']
                rankings.append((user, total))
            except:
                continue
                
        rankings.sort(key=lambda x: x[1], reverse=True)
        
        embed = discord.Embed(
            title=f"🏆 Top {len(rankings[:limit])} Usuários Mais Ricos",
            color=discord.Color.gold()
        )
        
        for idx, (user, wealth) in enumerate(rankings[:limit], 1):
            embed.add_field(
                name=f"{idx}. {user.display_name}",
                value=f"{wealth} 🪙",
                inline=False
            )
            
        await ctx.respond(embed=embed)


    # ============= FUNÇÕES AUXILIARES =============
    
    async def open_account(self, user) -> bool:
        """Abre uma conta para um usuário se não existir"""
        users = await self.get_bank_data()
        
        if str(user.id) not in users:
            users[str(user.id)] = {
                "wallet": 100,  # Saldo inicial
                "bank": 0,
                "bag": []
            }
            await self.save_bank_data(users)
            return True
        return False

    async def get_bank_data(self) -> Dict:
        """Carrega os dados do banco"""
        try:
            with open(self.BANK_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    async def save_bank_data(self, data: Dict) -> None:
        """Salva os dados no arquivo do banco"""
        with open(self.BANK_FILE, 'w') as f:
            json.dump(data, f, indent=4)

    async def update_bank(
        self, 
        user, 
        amount: int, 
        mode: str = 'wallet'
    ) -> Tuple[int, int]:
        """Atualiza o saldo do usuário"""
        users = await self.get_bank_data()
        users[str(user.id)][mode] += amount
        await self.save_bank_data(users)
        return (
            users[str(user.id)]['wallet'], 
            users[str(user.id)]['bank']
        )

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        if isinstance(error, CommandOnCooldown):
            await ctx.respond(f"⏳ Este comando está em cooldown. Tente novamente em `{error.retry_after:.1f}` segundos.", ephemeral=True)


def setup(bot):
    """Função de setup para a Cog"""
    bot.add_cog(Economy(bot))
