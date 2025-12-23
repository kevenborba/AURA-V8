import discord
import os
import asyncio
import traceback
from discord.ext import commands
from dotenv import load_dotenv
# Importação completa do banco de dados
from database.bot_db import create_db, get_db_connection, check_guild_config

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# ====================================================
# 🚀 CONFIGURAÇÃO OFICIAL (INTENTS)
# ====================================================
# Isso exige que as 3 chaves (Presence, Server Members, Message Content)
# estejam ativadas no Discord Developer Portal.
intents = discord.Intents.all()

class CityBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents, help_command=None, case_insensitive=True)
        self.db = None

    # ====================================================
    # 🔧 COMANDO DE EMERGÊNCIA: FIX BOT
    # ====================================================
    async def on_message(self, message):
        if message.author.bot: return
        
        # Apenas administradores
        if message.content == "!fix_bot" and message.author.guild_permissions.administrator:
            status_msg = await message.channel.send("🚨 **Iniciando Correção de Comandos...**")
            
            try:
                # 1. Limpa Comandos Globais (Remove Duplicatas Fantasmas)
                await status_msg.edit(content="🧹 [1/4] Limpando comandos globais antigos...")
                self.tree.clear_commands(guild=None)
                await self.tree.sync(guild=None) # Força a limpeza global

                # 2. Recarrega Cogs (Reler arquivos do disco)
                await status_msg.edit(content="🔄 [2/4] Recarregando módulos (Cogs)...")
                loaded = []
                if os.path.exists('./cogs'):
                    for filename in os.listdir('./cogs'):
                        if filename.endswith('.py'):
                            cog_name = f'cogs.{filename[:-3]}'
                            try:
                                await self.reload_extension(cog_name)
                                loaded.append(filename)
                            except commands.ExtensionNotLoaded:
                                await self.load_extension(cog_name)
                                loaded.append(filename)
                            except Exception as e:
                                await message.channel.send(f"⚠️ Erro ao carregar `{filename}`: {e}")

                # 3. Sincroniza Comandos APENAS para esta Guild (Instantâneo)
                await status_msg.edit(content=f"☁️ [3/4] Sincronizando Tree LOCAL (Cogs: {len(loaded)})...")
                
                # DEBUG CONSOLE
                print("📋 [DEBUG] Comandos identificados na Tree antes do Sync:")
                for cmd in self.tree.get_commands():
                    print(f"   - /{cmd.name} (Parent: {cmd.parent})")

                self.tree.copy_global_to(guild=message.guild)
                synced = await self.tree.sync(guild=message.guild)
                
                print(f"✅ [DEBUG] Comandos Sincronizados com Sucesso: {len(synced)}")
                for cmd in synced:
                    print(f"   + /{cmd.name} (ID: {cmd.id})")
                
                # 4. Finaliza
                await status_msg.edit(content=f"✅ **BOT CORRIGIDO!**\n\n"
                                            f"🧹 Globais: Limpos (Zero duplicatas)\n"
                                            f"📦 Módulos: {len(loaded)} recarregados\n"
                                            f"🔁 Locais: {len(synced)} sincronizados\n\n"
                                            f"⚠️ **IMPORTANTE:** Dê **Ctrl+R** agora para ver os comandos.")
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                await status_msg.edit(content=f"❌ **FALHA CRÍTICA:** {e}")
        
        await self.process_commands(message)

    async def setup_hook(self):
        print("⚙️ [SYSTEM] Iniciando setup...")
        
        # 1. Inicia Banco de Dados
        await create_db()
        self.db = await get_db_connection()
        print("✅ [DATABASE] Conexão estabelecida.")
        
        # 2. Carrega Cogs (Plugins)
        print("🔄 [SYSTEM] Carregando Cogs...")
        if os.path.exists('./cogs'):
            for filename in os.listdir('./cogs'):
                if filename.endswith('.py'):
                    try:
                        await self.load_extension(f'cogs.{filename[:-3]}')
                        print(f'   ├─ 🧩 {filename} carregado.')
                    except Exception as e:
                        print(f'   └─ ❌ FALHA CRÍTICA em {filename}:')
                        traceback.print_exc()

        # 3. Sincroniza Comandos (/)
        # DESATIVADO: Sync Global automático no startup causa duplicatas e lentidão
        print("☁️ [SYSTEM] Auto-Sync Global desativado para evitar duplicatas.")
        # try:
        #     await self.tree.sync() 
        #     print("✅ [SYSTEM] Sincronização concluída.")
        # except Exception as e:
        #     print(f"⚠️ [SYSTEM] Aviso na sincronização (Rate Limit ou Erro): {e}")

    async def close(self):
        if self.db: await self.db.close()
        await super().close()

    async def on_ready(self):
        print(f'''
        ╔════════════════════════════════════════╗
        ║  🤖 {self.user.name} ESTÁ ONLINE!      ║
        ║  ID: {self.user.id}                    ║
        ╚════════════════════════════════════════╝
        ''')
        
        # 4. Verifica Configurações dos Servidores
        print("🔍 [SYSTEM] Verificando configurações dos servidores...")
        for guild in self.guilds:
            if self.db:
                await check_guild_config(guild.id, self.db)
        print(f"✅ [SYSTEM] Configurações validadas para {len(self.guilds)} servidores.")
        
        # 5. Define Status
        try:
            await self.change_presence(activity=discord.Game(name="Gerenciando a Cidade"), status=discord.Status.online)
            print("🎮 [SYSTEM] Status definido com sucesso.")
        except Exception as e:
            print(f"⚠️ [SYSTEM] Não foi possível definir status: {e}")

    async def on_guild_join(self, guild):
        print(f"➕ [GUILD JOIN] Novo servidor: {guild.name} (ID: {guild.id})")
        if self.db:
            await check_guild_config(guild.id, self.db)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        print(f"❌ [ERROR] Comando '{ctx.command}' falhou: {error}")
        traceback.print_exc()
        try:
            await ctx.send(f"❌ **Erro no Comando:** `{error}`")
        except: pass

bot = CityBot()

if __name__ == '__main__':
    try:
        bot.run(TOKEN)
    except discord.errors.PrivilegedIntentsRequired:
        print("\n❌ ERRO DE PERMISSÃO:")
        print("Você esqueceu de ativar os 'Privileged Gateway Intents' no site do Discord Developer.")
        print("Vá em: https://discord.com/developers/applications -> Bot -> Privileged Gateway Intents")
        print("Ative as 3 opções (Presence, Server Members, Message Content) e salve.")