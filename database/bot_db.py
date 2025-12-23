import aiosqlite
import os

DB_NAME = "database/bot_data.db"

async def create_db():
    if not os.path.exists('database'):
        os.makedirs('database')

    async with aiosqlite.connect(DB_NAME) as db:
        # ====================================================
        # 1. CRIAÇÃO DAS TABELAS
        # ====================================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                guild_id INTEGER PRIMARY KEY,
                welcome_channel_id INTEGER, logs_channel_id INTEGER, sales_log_channel_id INTEGER,
                welcome_banner TEXT, welcome_color INTEGER DEFAULT 0,
                welcome_dm_active INTEGER DEFAULT 1,
                wl_btn_label TEXT, wl_btn_url TEXT, wl_btn_emoji TEXT,
                btn1_label TEXT, btn1_url TEXT, btn1_emoji TEXT,
                btn2_label TEXT, btn2_url TEXT, btn2_emoji TEXT,
                btn3_label TEXT, btn3_url TEXT, btn3_emoji TEXT,
                status_channel_id INTEGER, status_message_id INTEGER, server_ip TEXT,
                presence_interval INTEGER DEFAULT 60, presence_state TEXT DEFAULT 'online',
                sugg_channel_id INTEGER, sugg_count INTEGER DEFAULT 0,
                sugg_color INTEGER DEFAULT 0, sugg_up_emoji TEXT, sugg_down_emoji TEXT,
                bug_public_channel_id INTEGER, bug_staff_channel_id INTEGER, bug_count INTEGER DEFAULT 0,
                bug_emoji_public TEXT, bug_emoji_analyze TEXT, bug_emoji_fixed TEXT, bug_emoji_invalid TEXT,
                ticket_panel_channel_id INTEGER,
                ticket_category_id INTEGER,
                ticket_logs_id INTEGER,
                ticket_support_role_id INTEGER,
                ticket_count INTEGER DEFAULT 0,
                ticket_title TEXT, ticket_desc TEXT, ticket_banner TEXT, ticket_color INTEGER DEFAULT 0,
                ticket_viewer_url TEXT,
                tk_emoji_claim TEXT, tk_emoji_admin TEXT, tk_emoji_close TEXT, tk_emoji_cancel TEXT, tk_emoji_voice TEXT,
                rating_channel_id INTEGER,
                action_channel_id INTEGER,
                action_logs_channel_id INTEGER,
                action_role_id INTEGER,
                action_emoji_join TEXT, action_emoji_leave TEXT,
                action_emoji_win TEXT, action_emoji_loss TEXT,
                action_emoji_notify TEXT, action_emoji_edit TEXT,
                action_ranking_channel_id INTEGER,
                action_ranking_channel_id INTEGER,
                verification_role_id INTEGER,
                ticket_backup_webhook TEXT,
                verification_emoji TEXT,
                giveaway_color INTEGER DEFAULT 3447003,
                giveaway_emoji TEXT DEFAULT '🎉',
                sales_panel_color INTEGER DEFAULT 3066993,
                sales_btn_emoji TEXT DEFAULT '💰',
                sales_emoji_normal TEXT DEFAULT '💵',
                sales_emoji_partnership TEXT DEFAULT '🤝'
            )
        """)
        
        await db.execute("CREATE TABLE IF NOT EXISTS ticket_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, label TEXT, description TEXT, emoji TEXT, location_id INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS active_tickets (channel_id INTEGER PRIMARY KEY, guild_id INTEGER, user_id INTEGER, opened_at TEXT, claimed_by INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS staff_ratings (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, staff_id INTEGER, user_id INTEGER, stars INTEGER, comment TEXT, date TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS presence (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, activity_type TEXT, activity_text TEXT, activity_url TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS suggestion_votes (message_id INTEGER, user_id INTEGER, vote_type TEXT, guild_id INTEGER, PRIMARY KEY (message_id, user_id))")
        
        # Tabela de Ações da Facção
        await db.execute("""
            CREATE TABLE IF NOT EXISTS faction_actions (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                guild_id INTEGER,
                responsible_id INTEGER,
                action_name TEXT,
                date_time TEXT,
                slots INTEGER,
                status TEXT, -- OPEN, FULL, WIN, LOSS
                profit TEXT,
                participants TEXT, -- JSON List
                cancellations TEXT, -- JSON List
                mvp_id INTEGER
            )
        """)
        
        await db.execute("CREATE TABLE IF NOT EXISTS action_mvp_votes (message_id INTEGER, voter_id INTEGER, target_id INTEGER, guild_id INTEGER, PRIMARY KEY (message_id, voter_id))")
        
        # Tabela de Pings Ativos (Auto-Update)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_pings (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                guild_id INTEGER,
                user_id INTEGER
            )
        """)
        
        # Tabela de Templates de Embed
        await db.execute("""
            CREATE TABLE IF NOT EXISTS embed_templates (
                name TEXT,
                data TEXT, -- JSON Dump
                guild_id INTEGER,
                PRIMARY KEY (name, guild_id)
            )
        """)

        # ====================================================
        # 2. MIGRAÇÃO SEGURA
        # ====================================================
        cols_config = [
            ("tk_emoji_claim", "TEXT"), 
            ("tk_emoji_admin", "TEXT"), 
            ("tk_emoji_close", "TEXT"), 
            ("tk_emoji_cancel", "TEXT"), 
            ("tk_emoji_voice", "TEXT"),
            ("ticket_viewer_url", "TEXT"),
            ("rating_channel_id", "INTEGER"),
            ("action_channel_id", "INTEGER"),
            ("action_logs_channel_id", "INTEGER"),
            ("action_role_id", "INTEGER"),
            ("action_emoji_join", "TEXT"),
            ("action_emoji_leave", "TEXT"),
            ("action_emoji_win", "TEXT"),
            ("action_emoji_loss", "TEXT"),
            ("action_emoji_notify", "TEXT"),
            ("action_emoji_edit", "TEXT"),
            ("action_ranking_channel_id", "INTEGER"),
            ("verification_role_id", "INTEGER"),
            ("ticket_backup_webhook", "TEXT"),
            ("ticket_backup_webhook", "TEXT"),
            ("ticket_backup_webhook", "TEXT"),
            ("verification_emoji", "TEXT"),
            ("welcome_dm_active", "INTEGER DEFAULT 1"),
            ("giveaway_color", "INTEGER DEFAULT 3447003"),
            ("giveaway_emoji", "TEXT DEFAULT '🎉'"),
            ("sales_panel_color", "INTEGER DEFAULT 3066993"),
            ("sales_btn_emoji", "TEXT DEFAULT '💰'"),
            ("sales_log_channel_id", "INTEGER"),
            ("sales_emoji_normal", "TEXT DEFAULT '💵'"),
            ("sales_emoji_partnership", "TEXT DEFAULT '🤝'")
        ]
        
        async with db.execute("PRAGMA table_info(config)") as cursor:
            existing_config = [row[1] for row in await cursor.fetchall()]
        
        for c, t in cols_config:
            if c not in existing_config:
                try: 
                    print(f"🔄 [DATABASE] Adicionando coluna: {c}")
                    await db.execute(f"ALTER TABLE config ADD COLUMN {c} {t}")
                except: pass
                
        # Migração para faction_actions (MVP)
        async with db.execute("PRAGMA table_info(faction_actions)") as cursor:
            existing_actions = [row[1] for row in await cursor.fetchall()]
        if "mvp_id" not in existing_actions:
            try: await db.execute("ALTER TABLE faction_actions ADD COLUMN mvp_id INTEGER")
            except: pass

        # Migração para Giveaways (Title/Desc)
        async with db.execute("PRAGMA table_info(giveaways)") as cursor:
            existing_gw = [row[1] for row in await cursor.fetchall()]
        
        if "title" not in existing_gw:
            try: await db.execute("ALTER TABLE giveaways ADD COLUMN title TEXT")
            except: pass
        if "description" not in existing_gw:
            try: await db.execute("ALTER TABLE giveaways ADD COLUMN description TEXT")
            except: pass

        # Migrações extras
        async with db.execute("PRAGMA table_info(active_tickets)") as cursor:
            existing_tickets = [row[1] for row in await cursor.fetchall()]
        if "guild_id" not in existing_tickets:
            try: await db.execute("ALTER TABLE active_tickets ADD COLUMN guild_id INTEGER")
            except: pass

        async with db.execute("PRAGMA table_info(staff_ratings)") as cursor:
            existing_ratings = [row[1] for row in await cursor.fetchall()]
        if "guild_id" not in existing_ratings:
            try: await db.execute("ALTER TABLE staff_ratings ADD COLUMN guild_id INTEGER")
            except: pass

        async with db.execute("PRAGMA table_info(suggestion_votes)") as cursor:
            existing_votes = [row[1] for row in await cursor.fetchall()]
        if "guild_id" not in existing_votes:
            try: await db.execute("ALTER TABLE suggestion_votes ADD COLUMN guild_id INTEGER")
            except: pass

        async with db.execute("PRAGMA table_info(action_mvp_votes)") as cursor:
            existing_mvp_votes = [row[1] for row in await cursor.fetchall()]
        if "guild_id" not in existing_mvp_votes:
            try: await db.execute("ALTER TABLE action_mvp_votes ADD COLUMN guild_id INTEGER")
            except: pass

        # ====================================================
        # 3. INDICES
        # ====================================================
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cat_guild ON ticket_categories(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ticket_guild ON active_tickets(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rating_guild_staff ON staff_ratings(guild_id, staff_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sugg_guild ON suggestion_votes(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_mvp_guild ON action_mvp_votes(guild_id)")

        await db.commit()

async def get_db_connection():
    db = await aiosqlite.connect(DB_NAME)
    await db.execute("PRAGMA foreign_keys = ON") 
    return db

# A FUNÇÃO QUE FALTAVA ESTÁ AQUI EMBAIXO 👇
async def check_guild_config(guild_id, db_connection):
    await db_connection.execute("INSERT OR IGNORE INTO config (guild_id) VALUES (?)", (guild_id,))
    await db_connection.commit()