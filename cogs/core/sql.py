# cogs/core/sqlquery.py
import discord
from discord.ext import commands
from database import db

class SQLQueryModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Executar Consulta SQL")
        self.add_item(discord.ui.InputText(
            label="Consulta SQL",
            style=discord.InputTextStyle.long,
            placeholder="Ex: SELECT * FROM users WHERE id = 1;"
        ))

    async def callback(self, interaction: discord.Interaction):
        query = self.children[0].value.strip()
        if not query:
            await interaction.response.send_message(
                "⚠️ Nenhuma query fornecida.",
                ephemeral=True
            )
            return

        try:
            # Detecta se é SELECT ou modificação
            if query.lower().startswith("select"):
                results = db.execute_query(query)
                if not results:
                    await interaction.response.send_message(
                        "⚠️ Nenhum resultado encontrado.",
                        ephemeral=True
                    )
                    return

                # Monta string com resultados (limite 5 linhas)
                preview = ""
                for row in results[:5]:
                    preview += f"```{row}```\n"
                if len(results) > 5:
                    preview += f"... e mais {len(results)-5} resultados."

                await interaction.response.send_message(
                    f"✅ Resultado da consulta:\n{preview}",
                    ephemeral=True
                )
            else:
                # Queries de modificação: UPDATE, INSERT, DELETE
                with db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    conn.commit()
                    affected = cursor.rowcount
                await interaction.response.send_message(
                    f"✅ Query executada com sucesso! Linhas afetadas: {affected}",
                    ephemeral=True
                )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Erro ao executar query:\n```{e}```",
                ephemeral=True
            )


class SQLQueryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(name="sqlquery", description="Executa uma consulta SQL no banco")
    @commands.has_permissions(administrator=True)
    async def sqlquery(self, ctx: discord.ApplicationContext):
        """Abre um formulário para executar SQL (somente admin)."""
        await ctx.send_modal(SQLQueryModal())


def setup(bot: commands.Bot):
    bot.add_cog(SQLQueryCog(bot))
