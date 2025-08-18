# cogs/sql_query.py
import discord
from discord.ext import commands
from database import db


class SQLQueryModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Executar SQL Query")

        # Campo para digitar a query
        self.query_input = discord.TextInput(
            label="SQL Query",
            style=discord.TextStyle.paragraph,
            placeholder="Digite sua query SQL aqui...",
            required=True,
            max_length=2000,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction):
        sql = self.query_input.value.strip()

        try:
            # Executa apenas SELECT (seguro)
            if sql.lower().startswith("select"):
                results = db.execute_query(sql)

                if not results:
                    await interaction.response.send_message(
                        "✅ Query executada, mas sem resultados.",
                        ephemeral=True,
                    )
                    return

                # Formata os resultados em tabela simples
                header = " | ".join(results[0].keys())
                rows = [" | ".join(str(v) for v in row.values()) for row in results]
                preview = "\n".join(rows[:10])  # limita a 10 linhas

                formatted = f"```sql\n{header}\n{'-' * len(header)}\n{preview}\n```"
                if len(results) > 10:
                    formatted += f"\n⚠️ Mostrando apenas 10 de {len(results)} linhas."

                await interaction.response.send_message(formatted, ephemeral=True)

            else:
                # Para INSERT, UPDATE, DELETE, CREATE...
                with db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(sql)
                    conn.commit()
                    count = cursor.rowcount

                await interaction.response.send_message(
                    f"✅ Query executada com sucesso. ({count} linha(s) afetada(s))",
                    ephemeral=True,
                )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Erro ao executar a query:\n```{e}```",
                ephemeral=True,
            )


class SQLQueryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="sql",
        description="Executa uma consulta SQL no banco de dados",
    )
    @commands.has_permissions(administrator=True)
    async def sql(self, ctx: discord.ApplicationContext):
        """Abre um formulário (modal) para executar uma query SQL"""
        modal = SQLQueryModal()
        await ctx.send_modal(modal)


def setup(bot):
    bot.add_cog(SQLQueryCog(bot))
