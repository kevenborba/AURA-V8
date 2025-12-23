import discord
from discord import app_commands, ui
import time
try:
    import psutil
except ImportError:
    psutil = None
import datetime
import sys
import os
import io
import importlib
import matplotlib.pyplot as plt
from collections import deque
from discord.ext import commands, tasks

try:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config
except ImportError:
    pass

class General(commands.Cog):
    async def cog_load(self):
        self.bot.add_view(PingView(self))

    def cog_unload(self):
        self.auto_update_ping.cancel()

    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        self.latency_history = deque(maxlen=20)
        self.auto_update_ping.start()

    def generate_graph(self):
        """Gera um gráfico de latência em memória com eixos."""
        if not self.latency_history: return None
        
        fig, ax = plt.subplots(figsize=(8, 3)) 
        
        # Plotagem
        ax.plot(self.latency_history, color='#43b581', marker='o', markersize=4, linewidth=2)
        
        # Configuração dos Eixos
        ax.set_title("Latência (ms) - Últimos 20 Minutos", fontsize=12, color='white', pad=10)
        ax.set_ylabel("Ping (ms)", color='gray', fontsize=10)
        ax.set_xlabel("Tempo (minutos atrás)", color='gray', fontsize=10)
        
        # Grid leve
        ax.grid(True, linestyle='--', alpha=0.2)
        
        # Remove bordas desnecessárias
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color('gray')
        ax.spines['left'].set_color('gray')
        
        # Ajusta layout
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', transparent=True)
        buf.seek(0)
        plt.close(fig)
        return buf

    async def get_db_latency(self):
        start = time.perf_counter()
        try:
            async with self.bot.db.execute("SELECT 1"): 
                pass
            end = time.perf_counter()
            return round((end - start) * 1000, 2)
        except:
            return 0

    async def _build_status_embed(self, guild, requester_name):
        # Coleta de dados
        discord_ping = round(self.bot.latency * 1000)
        self.latency_history.append(discord_ping)
        
        db_ping = await self.get_db_latency()
        if psutil:
            cpu_usage = psutil.cpu_percent()
            ram_usage = psutil.virtual_memory().percent
        else:
            cpu_usage = 0
            ram_usage = 0
        
        # Lógica de Status
        if discord_ping < 150:
            status_emoji = "🟢"
        elif discord_ping < 350:
            status_emoji = "🟠"
        else:
            status_emoji = "🔴"

        embed = discord.Embed(title="🚀 Monitor de Sistema", color=0x000000, timestamp=datetime.datetime.now())
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.description = f"**Status do Sistema:** {status_emoji}\n**Uptime:** <t:{int(self.start_time)}:R>"
        
        embed.add_field(name="📡 Rede", value=f"**Ping API:** `{discord_ping}ms`\n**Ping DB:** `{db_ping}ms`", inline=True)
        embed.add_field(name="💻 Hardware", value=f"**CPU:** `{cpu_usage}%`\n**RAM:** `{ram_usage}%`", inline=True)
        embed.add_field(name="⚙️ Servidor", value=f"**Membros:** `{guild.member_count}`\n**Region:** `BR`", inline=True)
        embed.set_footer(text=f"Solicitado por {requester_name} • Atualiza a cada 1 min")

        return embed

    @tasks.loop(minutes=1)
    async def auto_update_ping(self):
        async with self.bot.db.execute("SELECT message_id, channel_id, guild_id, user_id FROM active_pings") as cursor:
            pings = await cursor.fetchall()

        for msg_id, chan_id, guild_id, user_id in pings:
            try:
                guild = self.bot.get_guild(guild_id)
                if not guild: continue
                
                channel = guild.get_channel(chan_id)
                if not channel: continue
                
                try:
                    message = await channel.fetch_message(msg_id)
                except discord.NotFound:
                    # Mensagem não existe mais, limpa do DB
                    await self.bot.db.execute("DELETE FROM active_pings WHERE message_id = ?", (msg_id,))
                    await self.bot.db.commit()
                    continue

                user = guild.get_member(user_id)
                requester_name = user.name if user else "Desconhecido"

                embed = await self._build_status_embed(guild, requester_name)
                
                # Gráfico
                graph_buf = self.generate_graph()
                files = []
                if graph_buf:
                    files.append(discord.File(graph_buf, filename="graph.png"))
                    embed.set_image(url="attachment://graph.png")
                else:
                    embed.set_image(url="https://raw.githubusercontent.com/bpevs/transparent-textures/master/1000x1.png")

                await message.edit(embed=embed, attachments=files)
            
            except Exception as e:
                print(f"❌ [PING] Erro ao atualizar msg {msg_id}: {e}")

    @auto_update_ping.before_loop
    async def before_auto_update(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="ping", description="📊 Exibe o painel de controle.")
    async def ping(self, interaction: discord.Interaction):
        importlib.reload(config) 
        await interaction.response.defer()
        await self.send_status_embed(interaction)

    async def send_status_embed(self, interaction: discord.Interaction, is_update=False):
        embed = await self._build_status_embed(interaction.guild, interaction.user.name)

        # Gráfico
        graph_buf = self.generate_graph()
        files = []
        if graph_buf:
            files.append(discord.File(graph_buf, filename="graph.png"))
            embed.set_image(url="attachment://graph.png")
        else:
            embed.set_image(url="https://raw.githubusercontent.com/bpevs/transparent-textures/master/1000x1.png")

        view = PingView(self)
        
        if is_update:
            await interaction.edit_original_response(embed=embed, view=view, attachments=files)
        else:
            msg = await interaction.followup.send(embed=embed, view=view, files=files)
            # Registra no DB para auto-update
            await self.bot.db.execute("INSERT OR REPLACE INTO active_pings (message_id, channel_id, guild_id, user_id) VALUES (?, ?, ?, ?)", 
                                      (msg.id, interaction.channel.id, interaction.guild.id, interaction.user.id))
            await self.bot.db.commit()

    @app_commands.command(name="help", description="📚 Lista todos os comandos disponíveis.")
    async def help_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        embed = discord.Embed(title="📚 Central de Ajuda", description="Aqui estão todos os comandos disponíveis no bot.", color=config.EMBED_COLOR)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_image(url="https://raw.githubusercontent.com/bpevs/transparent-textures/master/1000x1.png")
        
        for cog_name, cog in self.bot.cogs.items():
            commands_list = ""
            # Get Slash Commands
            for cmd in cog.walk_app_commands():
                # Skip subcommands if they are part of a group (handled by parent usually, but walk returns all)
                if hasattr(cmd, 'parent') and cmd.parent:
                    cmd_name = f"{cmd.parent.name} {cmd.name}"
                else:
                    cmd_name = cmd.name
                
                commands_list += f"**/{cmd_name}**: {cmd.description}\n"
            
            if commands_list:
                # Add Cog field
                embed.add_field(name=f"🧩 {cog_name}", value=commands_list, inline=False)
                
        await interaction.followup.send(embed=embed)

class PingView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @ui.button(label="Atualizar", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="ping_refresh_btn")
    async def refresh_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await self.cog.send_status_embed(interaction, is_update=True)

    @ui.button(label="Limpar", style=discord.ButtonStyle.secondary, emoji="🗑️", custom_id="ping_clear_btn")
    async def clear_button(self, interaction: discord.Interaction, button: ui.Button):
        # Remove do DB antes de deletar
        await self.cog.bot.db.execute("DELETE FROM active_pings WHERE message_id = ?", (interaction.message.id,))
        await self.cog.bot.db.commit()
        
        await interaction.message.delete()

async def setup(bot):
    await bot.add_cog(General(bot))