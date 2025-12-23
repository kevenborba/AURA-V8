import discord
from discord.ext import commands
from aiohttp import web
import os
import asyncio

class WebServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.site = None
        # Garante que a pasta existe para não dar erro ao iniciar o site
        if not os.path.exists('transcripts'):
            os.makedirs('transcripts')

    async def cog_load(self):
        """Inicia o servidor web assim que a Cog é carregada"""
        self.bot.loop.create_task(self.start_server())

    async def start_server(self):
        app = web.Application()
        
        # ROTA PRINCIPAL: Serve os arquivos HTML da pasta transcripts
        app.router.add_static('/transcripts/', path='./transcripts', name='transcripts')
        
        # ROTA DE TESTE: Para você saber se o site está online ao acessar a raiz
        app.router.add_get('/', self.handle_root)

        runner = web.AppRunner(app)
        await runner.setup()
        
        # CONFIGURAÇÃO SHARDCLOUD: PORTA 80
        # O host '0.0.0.0' é essencial para aceitar conexões externas
        try:
            self.site = web.TCPSite(runner, '0.0.0.0', 80)
            await self.site.start()
            print("🌍 [WEBSERVER] Site online! (ShardCloud Mode)")
        except PermissionError:
            print("❌ [WEBSERVER] Erro de Permissão: O container não permitiu usar a porta 80 (Falta root?).")
        except OSError as e:
            print(f"❌ [WEBSERVER] Porta 80 em uso ou indisponível: {e}")
        except Exception as e:
            print(f"❌ [WEBSERVER] Falha genérica ao iniciar site: {e}")

    async def handle_root(self, request):
        return web.Response(text="🤖 CityBot Transcript Server está Online!")

    async def cog_unload(self):
        """Desliga o site se o bot for desligado/reiniciado"""
        if self.site:
            await self.site.stop()

async def setup(bot):
    await bot.add_cog(WebServer(bot))