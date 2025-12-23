import discord
from discord.ext import commands
from discord import app_commands, ui
import datetime
import asyncio

INVISIBLE_WIDE_URL = "https://raw.githubusercontent.com/bpevs/transparent-textures/master/1000x1.png"

class Setagem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Migração DB
        print("🔍 [SETAGEM] Verificando tabelas...")
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS set_config (
                guild_id INTEGER PRIMARY KEY,
                channel_analysis INTEGER,
                channel_log INTEGER,
                role_verified INTEGER,
                role_unverified INTEGER,
                set_approve_emoji TEXT,
                set_reject_emoji TEXT
            )
        """)
        # Tabela de Cargos Selecionáveis
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS set_selectable_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                role_id INTEGER,
                label TEXT
            )
        """)
        await self.bot.db.commit()
        
        # Registra View Persistente
        self.bot.add_view(self.SetRequestView(self.bot, self))
        self.bot.add_view(SetagemDashboardView(self.bot, self))

    # ====================================================
    # 0. VIEW PERSISTENTE (SOLICITAR)
    # ====================================================
    class SetRequestView(ui.View):
        def __init__(self, bot, cog):
            super().__init__(timeout=None)
            self.bot = bot; self.cog = cog

        @ui.button(label="Solicitar Set", style=discord.ButtonStyle.primary, emoji="📝", custom_id="set_request_btn")
        async def request_btn(self, interaction: discord.Interaction, button: ui.Button):
            # Verifica se há cargos selecionáveis
            async with self.bot.db.execute("SELECT role_id, label FROM set_selectable_roles WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                roles = await cursor.fetchall()
            
            if roles:
                # Se tiver cargos, mostra Select Menu (Ephemeral, não precisa persistir)
                await interaction.response.send_message("Selecione o cargo que deseja:", view=self.cog.RoleSelectionView(self.bot, self.cog, roles), ephemeral=True)
            else:
                # Se não, vai direto pro modal
                await interaction.response.send_modal(self.cog.SetRequestModal(self.bot, self.cog))

    # ====================================================
    # 1. SELEÇÃO DE CARGO (VIEW)
    # ====================================================
    class RoleSelectionView(ui.View):
        def __init__(self, bot, cog, roles_data):
            super().__init__(timeout=60)
            self.bot = bot; self.cog = cog
            
            # Cria Select Menu Dinâmico
            options = []
            for r_id, label in roles_data:
                options.append(discord.SelectOption(label=label, value=str(r_id), emoji="👮"))
            
            select = ui.Select(placeholder="Selecione o Cargo Desejado...", min_values=1, max_values=1, options=options)
            select.callback = self.select_callback
            self.add_item(select)

        async def select_callback(self, interaction: discord.Interaction):
            role_id = int(interaction.data['values'][0])
            # Abre o Modal passando o cargo escolhido
            await interaction.response.send_modal(Setagem.SetRequestModal(self.bot, self.cog, role_id))

    # ====================================================
    # 2. SOLICITAÇÃO (MODAL)
    # ====================================================
    class SetRequestModal(ui.Modal, title="Solicitação de Setagem"):
        name = ui.TextInput(label="Nome Completo", placeholder="Seu nome RP", max_length=32)
        user_id = ui.TextInput(label="ID (Passaporte)", placeholder="Ex: 12345", max_length=10)
        recruiter = ui.TextInput(label="Quem te recrutou?", placeholder="Nome ou ID do recrutador", required=False)

        def __init__(self, bot, cog, selected_role_id=None):
            super().__init__()
            self.bot = bot; self.cog = cog; self.selected_role_id = selected_role_id

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            
            # Busca Config
            async with self.bot.db.execute("SELECT channel_analysis, set_approve_emoji, set_reject_emoji FROM set_config WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                row = await cursor.fetchone()
            
            if not row or not row[0]:
                return await interaction.followup.send("❌ Sistema não configurado (Canal de Análise faltando).", ephemeral=True)
            
            analysis_channel = interaction.guild.get_channel(row[0])
            emj_approve = row[1] if len(row) > 1 else None
            emj_reject = row[2] if len(row) > 2 else None
            if not analysis_channel:
                return await interaction.followup.send("❌ Canal de análise não encontrado.", ephemeral=True)

            # Busca info do cargo selecionado
            role_name = "Nenhum (Padrão)"
            if self.selected_role_id:
                role = interaction.guild.get_role(self.selected_role_id)
                if role: role_name = role.name

            # Monta Embed de Análise
            embed = discord.Embed(title="📝 Nova Solicitação de Set", color=0xf1c40f)
            embed.set_author(name=f"{interaction.user.display_name} ({interaction.user.id})", icon_url=interaction.user.display_avatar.url)
            embed.add_field(name="👤 Nome", value=self.name.value, inline=True)
            embed.add_field(name="🆔 Passaporte", value=self.user_id.value, inline=True)
            embed.add_field(name="👮 Cargo Solicitado", value=role_name, inline=False)
            embed.add_field(name="🤝 Recrutador", value=self.recruiter.value or "Ninguém", inline=False)
            embed.add_field(name="📅 Conta Criada", value=f"<t:{int(interaction.user.created_at.timestamp())}:R>", inline=False)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="Aguardando aprovação...")
            
            view = Setagem.AnalysisView(self.bot, self.cog, interaction.user.id, self.name.value, self.user_id.value, self.recruiter.value, self.selected_role_id, emj_approve, emj_reject)
            await analysis_channel.send(content=f"||{interaction.user.mention}||", embed=embed, view=view)
            
            await interaction.followup.send("✅ Solicitação enviada para análise!", ephemeral=True)

    # ====================================================
    # 3. ANÁLISE (VIEW)
    # ====================================================
    class AnalysisView(ui.View):
        def __init__(self, bot, cog, target_id, name, passport, recruiter, selected_role_id, emj_approve=None, emj_reject=None):
            super().__init__(timeout=None)
            self.bot = bot; self.cog = cog
            self.target_id = target_id
            self.name = name
            self.passport = passport
            self.recruiter = recruiter
            self.selected_role_id = selected_role_id
            
            # Atualiza Botões
            self.approve.emoji = emj_approve or "✅"
            self.reject.emoji = emj_reject or "✖️"

        @ui.button(label="Aprovar", style=discord.ButtonStyle.secondary, custom_id="set_btn_approve")
        async def approve(self, interaction: discord.Interaction, button: ui.Button):
            await interaction.response.defer()
            
            # Busca Config
            async with self.bot.db.execute("SELECT role_verified, role_unverified, channel_log FROM set_config WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                config = await cursor.fetchone()
                
            if not config: return await interaction.followup.send("❌ Configuração sumiu.", ephemeral=True)
            
            role_ver = interaction.guild.get_role(config[0]) if config[0] else None
            role_unver = interaction.guild.get_role(config[1]) if config[1] else None
            log_channel = interaction.guild.get_channel(config[2]) if config[2] else None
            
            target = interaction.guild.get_member(self.target_id)
            if not target:
                return await interaction.followup.send("❌ Usuário saiu do servidor.", ephemeral=True)

            # Ações
            try:
                # Troca Apelido
                new_nick = f"{self.passport} ・ {self.name}"
                await target.edit(nick=new_nick[:32])
                
                # Troca Cargos (Base + Selecionado)
                roles_to_add = []
                if role_ver: roles_to_add.append(role_ver)
                
                if self.selected_role_id:
                    sel_role = interaction.guild.get_role(self.selected_role_id)
                    if sel_role: roles_to_add.append(sel_role)
                
                if roles_to_add: await target.add_roles(*roles_to_add)
                if role_unver: await target.remove_roles(role_unver)
                
                # Feedback Visual
                embed = interaction.message.embeds[0]
                embed.color = 0x2ecc71
                embed.title = "✅ Solicitação Aprovada"
                embed.set_footer(text=f"Aprovado por {interaction.user.display_name}")
                
                for child in self.children: child.disabled = True
                await interaction.edit_original_response(embed=embed, view=self)
                
                # Log
                if log_channel:
                    role_name = "Padrão"
                    if self.selected_role_id:
                        r = interaction.guild.get_role(self.selected_role_id)
                        if r: role_name = r.name

                    log_embed = discord.Embed(title="✅ Setagem Realizada", color=0x2ecc71)
                    log_embed.set_author(name=f"Staff: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
                    log_embed.description = (
                        f"**Membro:** {target.mention}\n"
                        f"**Nome:** `{self.name}`\n"
                        f"**ID:** `{self.passport}`\n"
                        f"**Cargo:** `{role_name}`\n"
                        f"**Recrutador:** `{self.recruiter}`"
                    )
                    log_embed.set_thumbnail(url=target.display_avatar.url)
                    log_embed.set_image(url=INVISIBLE_WIDE_URL)
                    log_embed.timestamp = datetime.datetime.now()
                    await log_channel.send(embed=log_embed)

                try: await target.send(f"✅ **Parabéns!** Sua setagem no **{interaction.guild.name}** foi aprovada!")
                except: pass
                
            except Exception as e:
                await interaction.followup.send(f"⚠️ Erro parcial (Permissões?): {e}", ephemeral=True)

        @ui.button(label="Reprovar", style=discord.ButtonStyle.secondary, custom_id="set_btn_reject")
        async def reject(self, interaction: discord.Interaction, button: ui.Button):
            await interaction.response.send_modal(Setagem.RejectModal(self.bot, self.cog, self.target_id, interaction.message))

    class RejectModal(ui.Modal, title="Motivo da Reprovação"):
        reason = ui.TextInput(label="Motivo", placeholder="Ex: Nome inválido...", style=discord.TextStyle.paragraph)

        def __init__(self, bot, cog, target_id, original_message):
            super().__init__()
            self.bot = bot; self.cog = cog; self.target_id = target_id; self.original_msg = original_message

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer()
            target = interaction.guild.get_member(self.target_id)
            
            embed = self.original_msg.embeds[0]
            embed.color = 0xe74c3c
            embed.title = "✖️ Solicitação Reprovada"
            embed.add_field(name="Motivo", value=self.reason.value, inline=False)
            embed.set_footer(text=f"Reprovado por {interaction.user.display_name}")
            
            await self.original_msg.edit(embed=embed, view=None)
            
            if target:
                try: await target.send(f"✖️ Sua setagem no **{interaction.guild.name}** foi reprovada.\n**Motivo:** {self.reason.value}")
                except: pass
            
            await interaction.followup.send("✅ Reprovado com sucesso.", ephemeral=True)

    # ====================================================
    # 🎮 COMANDOS
    # ====================================================
    @app_commands.command(name="postar_setagem", description="📢 Envia o painel de solicitação de set.")
    @app_commands.checks.has_permissions(administrator=True)
    async def post_set_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Solicitação de Setagem", 
            description="Clique no botão abaixo para iniciar seu processo de verificação.\nSelecione seu cargo (se houver) e preencha seus dados.", 
            color=0x000000
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_image(url=INVISIBLE_WIDE_URL)
        embed.set_footer(text=f"Sistema de Verificação • {interaction.guild.name}")
        
        view = self.SetRequestView(self.bot, self)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Painel enviado com sucesso!", ephemeral=True)

    @app_commands.command(name="config_setagem", description="⚙️ Configura canais e cargos da setagem (Modo Rápido).")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_set(self, interaction: discord.Interaction, canal_analise: discord.TextChannel, canal_logs: discord.TextChannel, cargo_verificado: discord.Role):
        await self.bot.db.execute("""
            INSERT OR REPLACE INTO set_config (guild_id, channel_analysis, channel_log, role_verified)
            VALUES (?, ?, ?, ?)
        """, (interaction.guild.id, canal_analise.id, canal_logs.id, cargo_verificado.id))
        await self.bot.db.commit()
        await interaction.response.send_message(f"✅ Configuração salva!", ephemeral=True)

    @app_commands.command(name="painel_setagem", description="⚙️ Painel interativo de configuração da setagem.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setagem_dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.send_dashboard(interaction)

    async def send_dashboard(self, interaction):
        # Busca Config Atual
        async with self.bot.db.execute("SELECT channel_analysis, channel_log, role_verified, role_unverified, set_approve_emoji, set_reject_emoji FROM set_config WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
            row = await cursor.fetchone()
        
        # Se não houver config, define como None para todos
        if not row:
             row = (None, None, None, None, None, None)
        
        # Busca Cargos Selecionáveis
        async with self.bot.db.execute("SELECT role_id, label FROM set_selectable_roles WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
            sel_roles = await cursor.fetchall()
        
        c_analysis = interaction.guild.get_channel(row[0]) if row and row[0] else None
        c_logs = interaction.guild.get_channel(row[1]) if row and row[1] else None
        r_ver = interaction.guild.get_role(row[2]) if row and row[2] else None
        r_unver = interaction.guild.get_role(row[3]) if row and row[3] else None
        emj_app = row[4] or "✅ (Padrão)"
        emj_rej = row[5] or "✖️ (Padrão)"

        embed = discord.Embed(title="⚙️ Configuração de Setagem", color=0x2b2d31)
        embed.description = "Use os menus abaixo para configurar o sistema de setagem."
        
        embed.add_field(name="🕵️ Canal de Análise", value=c_analysis.mention if c_analysis else "❌ Não definido", inline=True)
        embed.add_field(name="📜 Canal de Logs", value=c_logs.mention if c_logs else "❌ Não definido", inline=True)
        embed.add_field(name="✅ Cargo Verificado", value=r_ver.mention if r_ver else "❌ Não definido", inline=True)
        embed.add_field(name="🔒 Cargo Não Verificado", value=r_unver.mention if r_unver else "➖ Nenhum", inline=True)
        embed.add_field(name="🙂 Emojis", value=f"Aprovar: {emj_app}\nReprovar: {emj_rej}", inline=True)
        
        sel_roles_txt = ""
        if sel_roles:
            for rid, lbl in sel_roles:
                r = interaction.guild.get_role(rid)
                sel_roles_txt += f"• {lbl} -> {r.mention if r else 'Deletado'}\n"
        else:
            sel_roles_txt = "Nenhum (Vai direto pro Modal)"
            
        embed.add_field(name="📋 Cargos Selecionáveis", value=sel_roles_txt, inline=False)
        
        view = SetagemDashboardView(self.bot, self)
        await interaction.followup.send(embed=embed, view=view)

class SetagemDashboardView(ui.View):
    def __init__(self, bot, cog):
        super().__init__(timeout=None)
        self.bot = bot; self.cog = cog

    @ui.select(cls=ui.ChannelSelect, placeholder="Selecione o Canal de Análise", channel_types=[discord.ChannelType.text], min_values=1, max_values=1, custom_id="set_sel_analysis")
    async def select_analysis(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        await self.update_config(interaction, "channel_analysis", select.values[0].id)

    @ui.select(cls=ui.ChannelSelect, placeholder="Selecione o Canal de Logs", channel_types=[discord.ChannelType.text], min_values=1, max_values=1, custom_id="set_sel_logs")
    async def select_logs(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        await self.update_config(interaction, "channel_log", select.values[0].id)

    @ui.select(cls=ui.RoleSelect, placeholder="Selecione o Cargo Verificado (Ganhar)", min_values=1, max_values=1, custom_id="set_sel_verified")
    async def select_verified(self, interaction: discord.Interaction, select: ui.RoleSelect):
        await self.update_config(interaction, "role_verified", select.values[0].id)

    @ui.select(cls=ui.RoleSelect, placeholder="Selecione o Cargo Não Verificado (Perder)", min_values=0, max_values=1, custom_id="set_sel_unverified")
    async def select_unverified(self, interaction: discord.Interaction, select: ui.RoleSelect):
        val = select.values[0].id if select.values else None
        await self.update_config(interaction, "role_unverified", val)

    @ui.button(label="Adicionar Cargo Selecionável", style=discord.ButtonStyle.blurple, emoji="➕", custom_id="set_btn_add_sel")
    async def add_sel_role(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AddSelectableRoleModal(self.bot, self.cog, interaction))

    @ui.button(label="Limpar Cargos Selecionáveis", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="set_btn_clear_sel")
    async def clear_sel_roles(self, interaction: discord.Interaction, button: ui.Button):
        await self.bot.db.execute("DELETE FROM set_selectable_roles WHERE guild_id = ?", (interaction.guild.id,))
        await self.bot.db.commit()
        await self.cog.send_dashboard(interaction)

    @ui.button(label="Configurar Emojis", style=discord.ButtonStyle.secondary, emoji="🙂", custom_id="set_btn_emojis", row=2)
    async def config_emojis(self, interaction: discord.Interaction, button: ui.Button):
        # Fetch current emojis for default values
        async with self.bot.db.execute("SELECT set_approve_emoji, set_reject_emoji FROM set_config WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
            row = await cursor.fetchone()
        cur_app = row[0] if row else ""
        cur_rej = row[1] if row else ""
        await interaction.response.send_modal(SetEmojiConfigModal(self.bot, self.cog, interaction, cur_app, cur_rej))

    async def update_config(self, interaction, column, value):
        await interaction.response.defer()
        await self.bot.db.execute("INSERT OR IGNORE INTO set_config (guild_id) VALUES (?)", (interaction.guild.id,))
        await self.bot.db.execute(f"UPDATE set_config SET {column} = ? WHERE guild_id = ?", (value, interaction.guild.id))
        await self.bot.db.commit()
        await self.cog.send_dashboard(interaction)

class AddSelectableRoleModal(ui.Modal, title="Adicionar Cargo Selecionável"):
    role_id = ui.TextInput(label="ID do Cargo", placeholder="Ative o modo dev")
    label = ui.TextInput(label="Nome no Menu", placeholder="Ex: Soldado, Médico...")

    def __init__(self, bot, cog, origin):
        super().__init__()
        self.bot = bot; self.cog = cog; self.origin = origin

    async def on_submit(self, interaction: discord.Interaction):
        try: rid = int(self.role_id.value)
        except: return await interaction.response.send_message("ID inválido", ephemeral=True)
        
        await self.bot.db.execute("INSERT INTO set_selectable_roles (guild_id, role_id, label) VALUES (?, ?, ?)", 
                                  (interaction.guild.id, rid, self.label.value))
        await self.bot.db.commit()
        await interaction.response.send_message("✅ Adicionado!", ephemeral=True)
        try: await self.cog.send_dashboard(self.origin)
        except: pass

class SetEmojiConfigModal(ui.Modal, title="Configurar Emojis"):
    def __init__(self, bot, cog, origin, cur_app, cur_rej):
        super().__init__()
        self.bot = bot; self.cog = cog; self.origin = origin
        
        self.emj_app = ui.TextInput(label="Emoji de Aprovação", placeholder="Ex: ✅", default=cur_app or "")
        self.emj_rej = ui.TextInput(label="Emoji de Reprovação", placeholder="Ex: ✖️", default=cur_rej or "")
        self.add_item(self.emj_app)
        self.add_item(self.emj_rej)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.execute("INSERT OR IGNORE INTO set_config (guild_id) VALUES (?)", (interaction.guild.id,))
        await self.bot.db.execute("UPDATE set_config SET set_approve_emoji = ?, set_reject_emoji = ? WHERE guild_id = ?", 
                                  (self.emj_app.value, self.emj_rej.value, interaction.guild.id))
        await self.bot.db.commit()
        await interaction.followup.send("✅ Emojis salvos!", ephemeral=True)
        await self.cog.send_dashboard(self.origin)

async def setup(bot):
    await bot.add_cog(Setagem(bot))
