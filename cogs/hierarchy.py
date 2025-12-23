import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import datetime
import asyncio

INVISIBLE_WIDE_URL = "https://raw.githubusercontent.com/bpevs/transparent-textures/master/1000x1.png"

class Hierarchy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_update.start()

    def cog_unload(self):
        self.daily_update.cancel()

    async def cog_load(self):
        # Migração DB
        print("🔍 [HIERARCHY] Verificando tabelas...")
        
        # Tabela de Cargos
        try:
            async with self.bot.db.execute("SELECT group_name FROM hierarchy_roles LIMIT 1") as cursor: pass
        except:
            print("⚠️ [HIERARCHY] Atualizando tabela de cargos...")
            try:
                await self.bot.db.execute("""
                    CREATE TABLE IF NOT EXISTS hierarchy_roles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER,
                        role_id INTEGER,
                        label TEXT,
                        priority INTEGER,
                        group_name TEXT DEFAULT 'Principal'
                    )
                """)
                try: await self.bot.db.execute("ALTER TABLE hierarchy_roles ADD COLUMN group_name TEXT DEFAULT 'Principal'")
                except: pass
                await self.bot.db.commit()
            except Exception as e: print(f"❌ [HIERARCHY] Erro migração roles: {e}")

        # Tabela de Mensagens Ativas (Para Auto-Update)
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS hierarchy_messages (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                guild_id INTEGER,
                group_name TEXT
            )
        """)
        await self.bot.db.commit()
        
        # Registra View Persistente
        self.bot.add_view(RefreshHierarchyView(self.bot, self))
        self.bot.add_view(HierarchyConfigView(self.bot, self))

    # ====================================================
    # 🔄 AUTO-UPDATE (00:00)
    # ====================================================
    # Timezone pode variar dependendo do servidor, mas 00:00 UTC é um bom padrão.
    # Se precisar de BRT (UTC-3), seria time=datetime.time(hour=3)
    @tasks.loop(time=datetime.time(hour=3, minute=0)) # 03:00 UTC = 00:00 BRT (aprox)
    async def daily_update(self):
        print("🔄 [HIERARCHY] Iniciando atualização diária...")
        async with self.bot.db.execute("SELECT message_id, channel_id, guild_id, group_name FROM hierarchy_messages") as cursor:
            messages = await cursor.fetchall()
            
        for msg_id, chan_id, guild_id, group_name in messages:
            try:
                guild = self.bot.get_guild(guild_id)
                if not guild: continue
                
                channel = guild.get_channel(chan_id)
                if not channel: continue
                
                try:
                    message = await channel.fetch_message(msg_id)
                except discord.NotFound:
                    # Mensagem deletada, remove do DB
                    await self.bot.db.execute("DELETE FROM hierarchy_messages WHERE message_id = ?", (msg_id,))
                    await self.bot.db.commit()
                    continue
                
                embed = await self._build_hierarchy_embed(guild, group_name)
                if embed:
                    await message.edit(embed=embed)
                    
            except Exception as e:
                print(f"❌ [HIERARCHY] Erro ao atualizar msg {msg_id}: {e}")

    @daily_update.before_loop
    async def before_daily_update(self):
        await self.bot.wait_until_ready()

    # ====================================================
    # 🏗️ CONSTRUTOR DE EMBED
    # ====================================================
    async def _build_hierarchy_embed(self, guild, group_name="Principal"):
        # Busca Config do Grupo
        async with self.bot.db.execute("SELECT role_id, label FROM hierarchy_roles WHERE guild_id = ? AND group_name = ? ORDER BY priority ASC", (guild.id, group_name)) as cursor:
            rows = await cursor.fetchall()
            
        if not rows:
            return None

        embed = discord.Embed(title=f"🏛️ {group_name.upper()}", color=0x2b2d31)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else self.bot.user.display_avatar.url)
        embed.set_image(url=INVISIBLE_WIDE_URL)
        
        description = ""
        
        for role_id, label in rows:
            role = guild.get_role(role_id)
            if not role: continue
            
            members = role.members
            if not members: continue
            
            # Ordena e formata
            members.sort(key=lambda m: m.display_name)
            
            # Cabeçalho do Cargo
            description += f"\n**{label}**\n" # Ex: **👑 LIDERANÇA**
            
            # Lista de Membros (Estilo Árvore)
            for i, member in enumerate(members):
                is_last = (i == len(members) - 1)
                prefix = "╰" if is_last else "├"
                description += f"> `{prefix}` {member.mention}\n"
        
        if not description:
            description = "*Nenhum membro encontrado nos cargos configurados.*"
            
        embed.description = description
        embed.set_footer(text=f"Atualizado em {datetime.datetime.now().strftime('%d/%m às %H:%M')}")
        
        return embed

    # ====================================================
    # 🎮 COMANDOS
    # ====================================================
    @app_commands.command(name="hierarquia", description="Exibe a hierarquia (lista de membros).")
    @app_commands.describe(grupo="Nome do grupo (Ex: Principal, Tatico). Deixe vazio para Principal.")
    async def show_hierarchy(self, interaction: discord.Interaction, grupo: str = "Principal"):
        await interaction.response.defer()
        
        embed = await self._build_hierarchy_embed(interaction.guild, grupo)
        
        if not embed:
            return await interaction.followup.send(f"❌ Grupo '{grupo}' não encontrado ou vazio. Use `/painel_hierarquia`.")
            
        view = RefreshHierarchyView(self.bot, self)
        message = await interaction.followup.send(embed=embed, view=view)
        
        # Salva para Auto-Update
        await self.bot.db.execute("INSERT OR REPLACE INTO hierarchy_messages (message_id, channel_id, guild_id, group_name) VALUES (?, ?, ?, ?)", 
                                  (message.id, interaction.channel.id, interaction.guild.id, grupo))
        await self.bot.db.commit()

    @app_commands.command(name="painel_hierarquia", description="⚙️ Configura a hierarquia (Grupos e Cargos).")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_hierarchy(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.send_panel(interaction)

    async def send_panel(self, interaction):
        # Lista cargos agrupados
        async with self.bot.db.execute("SELECT id, role_id, label, priority, group_name FROM hierarchy_roles WHERE guild_id = ? ORDER BY group_name, priority ASC", (interaction.guild.id,)) as cursor:
            rows = await cursor.fetchall()
            
        embed = discord.Embed(title="⚙️ Configuração de Hierarquia", color=0x2b2d31)
        
        if not rows:
            embed.description = "*Nenhuma configuração encontrada.*"
        else:
            desc = ""
            current_group = None
            for r in rows:
                if r[4] != current_group:
                    current_group = r[4]
                    desc += f"\n📂 **{current_group}**\n"
                
                role = interaction.guild.get_role(r[1])
                role_name = role.mention if role else f"ID: {r[1]}"
                desc += f"`{r[3]}`. **{r[2]}** -> {role_name} (ID DB: {r[0]})\n"
            embed.description = desc

        view = HierarchyConfigView(self.bot, self)
        await interaction.followup.send(embed=embed, view=view)

class RefreshHierarchyView(ui.View):
    def __init__(self, bot, cog):
        super().__init__(timeout=None)
        self.bot = bot; self.cog = cog

    @ui.button(label="Atualizar", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="hier_refresh")
    async def refresh(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        
        # Busca qual grupo é essa mensagem
        async with self.bot.db.execute("SELECT group_name FROM hierarchy_messages WHERE message_id = ?", (interaction.message.id,)) as cursor:
            row = await cursor.fetchone()
            
        group_name = row[0] if row else "Principal"
        
        embed = await self.cog._build_hierarchy_embed(interaction.guild, group_name)
        if embed:
            await interaction.edit_original_response(embed=embed)
        else:
            await interaction.followup.send("❌ Erro ao atualizar (Grupo não encontrado?).", ephemeral=True)

class HierarchyConfigView(ui.View):
    def __init__(self, bot, cog):
        super().__init__(timeout=None)
        self.bot = bot; self.cog = cog

    @ui.button(label="Adicionar Cargo", style=discord.ButtonStyle.green, emoji="➕", custom_id="hier_btn_add")
    async def add_role(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AddRoleModal(self.bot, self.cog, interaction))

    @ui.button(label="Remover Item (ID)", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="hier_btn_remove")
    async def remove_item(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RemoveRoleModal(self.bot, self.cog, interaction))

class AddRoleModal(ui.Modal, title="Adicionar Cargo"):
    group_name = ui.TextInput(label="Nome do Grupo", default="Principal", placeholder="Ex: Principal, Tatico...")
    role_id = ui.TextInput(label="ID do Cargo", placeholder="Ative o modo dev para pegar ID")
    label = ui.TextInput(label="Título na Lista", placeholder="Ex: Líderes")
    priority = ui.TextInput(label="Prioridade (1 = Topo)", placeholder="Número")

    def __init__(self, bot, cog, origin):
        super().__init__()
        self.bot = bot; self.cog = cog; self.origin = origin

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rid = int(self.role_id.value)
            prio = int(self.priority.value)
        except: return await interaction.response.send_message("❌ ID e Prioridade devem ser números.", ephemeral=True)
        
        await self.bot.db.execute("INSERT INTO hierarchy_roles (guild_id, role_id, label, priority, group_name) VALUES (?, ?, ?, ?, ?)", 
                                  (interaction.guild.id, rid, self.label.value, prio, self.group_name.value))
        await self.bot.db.commit()
        await interaction.response.send_message("✅ Adicionado!", ephemeral=True)
        try: await self.cog.send_panel(self.origin)
        except: pass

class RemoveRoleModal(ui.Modal, title="Remover Item"):
    db_id = ui.TextInput(label="ID do Banco (Veja no Painel)", placeholder="Número ao lado do cargo")

    def __init__(self, bot, cog, origin):
        super().__init__()
        self.bot = bot; self.cog = cog; self.origin = origin

    async def on_submit(self, interaction: discord.Interaction):
        try: did = int(self.db_id.value)
        except: return await interaction.response.send_message("❌ Deve ser um número.", ephemeral=True)
        
        await self.bot.db.execute("DELETE FROM hierarchy_roles WHERE id = ? AND guild_id = ?", (did, interaction.guild.id))
        await self.bot.db.commit()
        await interaction.response.send_message("✅ Removido!", ephemeral=True)
        try: await self.cog.send_panel(self.origin)
        except: pass

async def setup(bot):
    await bot.add_cog(Hierarchy(bot))
