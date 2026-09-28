import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST")


async def create_db_pool():
    return await asyncpg.create_pool(
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        host=DB_HOST
    )


async def init_db(pool):
    async with pool.acquire() as conn:
        # Asosiy hikmatlar jadvaliga category ustuni qo'shildi
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS quotes (
            id SERIAL PRIMARY KEY,
            text TEXT NOT NULL,
            author VARCHAR(100) DEFAULT 'Noma''lum',
            category VARCHAR(50) DEFAULT 'hikmat'
        );
        ''')

        # Agar jadval oldindan bor bo'lsa va category ustuni bo'lmasa, uni qo'shish (Xavfsizlik uchun)
        await conn.execute('''
        ALTER TABLE quotes ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'hikmat';
        ''')

        # Admin tasdiqlashini kutayotgan takliflar jadvali
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS pending_quotes (
            id SERIAL PRIMARY KEY,
            text TEXT NOT NULL,
            user_id BIGINT NOT NULL,
            user_name VARCHAR(150)
        );
        ''')

        count = await conn.fetchval('SELECT COUNT(*) FROM quotes')
        if count == 0:
            # Boshlang'ich ma'lumotlar (Kategoriyalari bilan)
            quotes = [
                ("Ilm qaytarish bilan, amal ixlos bilan tirikdir.", "Alisher Navoiy", "hikmat"),
                ("Muvaffaqiyat kaliti — xatolardan qo'rqmaslikda.", "Donishmand", "hikmat"),
                ("Eng katta g'alaba — o'z nafsi ustidan qozonilgan g'alabadir.", "Donishmand", "hikmat"),
                # Motivatsiya uchun yangi gaplar:
                ("Yiqilish — bu mag'lubiyat emas. Turishdan bosh tortish — mag'lubiyatdir!", "Noma'lum", "motivatsiya"),
                ("Bugun bajarmasangiz, ertaga orzularingiz boshqalariki bo'ladi. Hozir boshlang!", "Donishmand", "motivatsiya"),
                ("Chegaralar faqat sizning miyangizda mavjud. Siz o'ylaganingizdan ham kuchlisiz!", "Noma'lum", "motivatsiya"),
                ("Muvaffaqiyat har kuni takrorlanadigan kichik harakatlarning yig'indisidir.", "Robert Koler", "motivatsiya")
            ]
            await conn.executemany(
                'INSERT INTO quotes (text, author, category) VALUES ($1, $2, $3);', quotes
            )


async def get_random_quote(pool, category="hikmat"):
    """Kategoriya bo'yicha tasodifiy xabar olish"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT text, author FROM quotes WHERE category = $1 ORDER BY RANDOM() LIMIT 1;',
            category
        )
        if row:
            return f"«{row['text']}»\n\n✍️ — {row['author']}"
        return None


async def get_quotes_count(pool):
    async with pool.acquire() as conn:
        return await conn.fetchval('SELECT COUNT(*) FROM quotes;')


async def add_new_quote(pool, text, author, category="hikmat"):
    """Yangi gap qo'shishda kategoriya ham saqlanadi"""
    async with pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO quotes (text, author, category) VALUES ($1, $2, $3);',
            text, author, category
        )


async def add_pending_quote(pool, text, user_id, user_name):
    async with pool.acquire() as conn:
        return await conn.fetchval(
            'INSERT INTO pending_quotes (text, user_id, user_name) VALUES ($1, $2, $3) RETURNING id;',
            text, user_id, user_name
        )

async def get_pending_quote(pool, quote_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT text, user_id FROM pending_quotes WHERE id = $1;', quote_id)

async def delete_pending_quote(pool, quote_id):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM pending_quotes WHERE id = $1;', quote_id)
