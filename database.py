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
        # Asosiy hikmatlar jadvali
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS quotes (
            id SERIAL PRIMARY KEY,
            text TEXT NOT NULL,
            author VARCHAR(100) DEFAULT 'Noma''lum'
        );
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
            quotes = [
                ("Ilm qaytarish bilan, amal ixlos bilan tirikdir.", "Alisher Navoiy"),
                ("Muvaffaqiyat kaliti — xatolardan qo'rqmaslikda.", "Donishmand"),
                ("Vaqt — bu sizning hayotingiz. Uni bekorchi narsalarga sarflamang.", "Noma'lum"),
                ("Eng katta g'alaba — o'z nafsi ustidan qozonilgan g'alabadir.", "Donishmand"),
                ("Kuchsizlar hech qachon kechira olmaydilar. Kechirimli bo'lish kuchlilarga xosdir.", "Mahatma Gandi")
            ]
            await conn.executemany(
                'INSERT INTO quotes (text, author) VALUES ($1, $2);', quotes
            )


async def get_random_quote(pool):
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT text, author FROM quotes ORDER BY RANDOM() LIMIT 1;')
        if row:
            return f"«{row['text']}»\n\n✍️ — {row['author']}"
        return None


async def get_quotes_count(pool):
    async with pool.acquire() as conn:
        return await conn.fetchval('SELECT COUNT(*) FROM quotes;')


async def add_new_quote(pool, text, author):
    async with pool.acquire() as conn:
        await conn.execute('INSERT INTO quotes (text, author) VALUES ($1, $2);', text, author)


# --- YANGI QO'SHILGAN FUNKSIYALAR ---

async def add_pending_quote(pool, text, user_id, user_name):
    """Foydalanuvchi taklif qilgan gapni vaqtincha saqlash"""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            'INSERT INTO pending_quotes (text, user_id, user_name) VALUES ($1, $2, $3) RETURNING id;',
            text, user_id, user_name
        )

async def get_pending_quote(pool, quote_id):
    """ID bo'yicha taklif qilingan gapni olish"""
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT text, user_id FROM pending_quotes WHERE id = $1;', quote_id)

async def delete_pending_quote(pool, quote_id):
    """Tasdiqlangan yoki rad etilgan gapni vaqtinchalik jadvaldan o'chirish"""
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM pending_quotes WHERE id = $1;', quote_id)
