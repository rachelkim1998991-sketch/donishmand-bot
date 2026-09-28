import time
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, html, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv

from database import (
    create_db_pool, init_db, get_random_quote, get_quotes_count, add_new_quote,
    add_pending_quote, get_pending_quote, delete_pending_quote,
    add_user_if_not_exists, get_users_count
)


load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

LAST_ACTIVITY_TIME = time.time()

logging.basicConfig(level=logging.INFO)


class QuoteSuggestion(StatesGroup):
    waiting_for_text = State()
    waiting_for_category = State()


class AddQuoteStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_author = State()


class AdminEditStates(StatesGroup):
    waiting_for_edited_text = State()


def get_user_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎲 Tasodifiy hikmat", callback_data="get_random_quote"),
        InlineKeyboardButton(text="🔥 Motivatsiya", callback_data="get_motivation")
    )
    builder.row(
        InlineKeyboardButton(text="✍️ Aqlli gap qo'shish", callback_data="suggest_quote")
    )
    return builder.as_markup()


def get_category_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🧠 Hikmatli gap", callback_data="set_cat_hikmat"),
        InlineKeyboardButton(text="🔥 Motivatsiya", callback_data="set_cat_motivatsiya")
    )
    return builder.as_markup()


def get_approval_keyboard(quote_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{quote_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{quote_id}")
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_req_{quote_id}")
    )
    return builder.as_markup()


def get_admin_edit_category_keyboard(quote_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🧠 Hikmat qilib qo'shish", callback_data=f"save_edit_{quote_id}_hikmat"),
        InlineKeyboardButton(text="🔥 Motivatsiya qilib qo'shish", callback_data=f"save_edit_{quote_id}_motivatsiya")
    )
    return builder.as_markup()


def get_admin_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="➕ Yangi gap qo'shish", callback_data="admin_add"))
    return builder.as_markup()


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    db_pool = await create_db_pool()
    await init_db(db_pool)

    @dp.message(CommandStart())
    async def command_start_handler(message: Message, state: FSMContext) -> None:
        global LAST_ACTIVITY_TIME
        await state.clear()

        current_time = time.time()
        bot_was_sleeping = (current_time - LAST_ACTIVITY_TIME) > 300

        LAST_ACTIVITY_TIME = current_time

        try:
            await add_user_if_not_exists(db_pool, message.from_user.id, message.from_user.full_name)
        except Exception as e:
            logging.error(f"Foydalanuvchini saqlashda xato: {e}")

        try:
            quote = await get_random_quote(db_pool, category="hikmat")
        except Exception as e:
            logging.error(f"Bazadan hikmat olishda xato: {e}")
            quote = "«Ilm qaytarish bilan, amal ixlos bilan tirikdir.»\n\n✍️ — Alisher Navoiy"

        welcome_text = ""

        if bot_was_sleeping:
            welcome_text += (
                f"😴 {html.italic('Uyg`onish jarayoni muvaffaqiyatli yakunlandi!')}\n"
                f"Uxlab qolgandim 😁 Meni uyg`otganingiz uchun rahmat! ✨\n\n"
            )

        welcome_text += f"Assalomu alaykum, {html.bold(message.from_user.full_name)}!\n\n"
        welcome_text += f"Kun hikmati:\n{quote}"

        await message.answer(
            text=welcome_text,
            parse_mode="HTML",
            reply_markup=get_user_keyboard()
        )

    @dp.callback_query(F.data == "get_random_quote")
    async def callback_random_quote(callback: CallbackQuery):
        try:
            quote = await get_random_quote(db_pool, category="hikmat")
        except Exception:
            quote = "«Ilm qaytarish bilan, amal ixlos bilan tirikdir.»\n\n✍️ — Alisher Navoiy"

        welcome_text = f"Kun hikmati:\n{quote}"
        try:
            await callback.message.edit_text(
                text=welcome_text,
                parse_mode="HTML",
                reply_markup=get_user_keyboard()
            )
        except Exception:
            pass
        await callback.answer()

    @dp.callback_query(F.data == "get_motivation")
    async def callback_motivation(callback: CallbackQuery):
        try:
            quote = await get_random_quote(db_pool, category="motivatsiya")
        except Exception:
            quote = None

        if not quote:
            welcome_text = f"🔥 {html.bold('Siz uchun motivatsiya:')}\n\nHozircha motivatsion gaplar mavjud emas 😔"
        else:
            welcome_text = f"🔥 {html.bold('Siz uchun motivatsiya:')}\n\n{quote}"

        try:
            await callback.message.edit_text(
                text=welcome_text,
                parse_mode="HTML",
                reply_markup=get_user_keyboard()
            )
        except Exception:
            pass
        await callback.answer()


    @dp.callback_query(F.data == "suggest_quote")
    async def start_suggestion(callback: CallbackQuery, state: FSMContext):
        await state.set_state(QuoteSuggestion.waiting_for_text)
        await callback.message.answer(text="✍️ Marhamat, botga qo'shmoqchi bo'lgan gapni yozib yuboring:")
        await callback.answer()

    @dp.message(QuoteSuggestion.waiting_for_text)
    async def receive_suggestion_text(message: Message, state: FSMContext):
        await state.update_data(suggest_text=message.text)
        await state.set_state(QuoteSuggestion.waiting_for_category)

        await message.answer(
            text="Kategoriyani tanlang:\nBu hikmatli gapmi yoki motivatsiyami?",
            reply_markup=get_category_keyboard()
        )

    @dp.callback_query(QuoteSuggestion.waiting_for_category, F.data.startswith("set_cat_"))
    async def receive_suggestion_category(callback: CallbackQuery, state: FSMContext):
        chosen_cat = callback.data.replace("set_cat_", "")
        user_data = await state.get_data()
        user_text = user_data.get("suggest_text")
        await state.clear()

        full_text_with_cat = f"[{chosen_cat}] {user_text}"

        quote_id = await add_pending_quote(
            db_pool,
            full_text_with_cat,
            callback.from_user.id,
            callback.from_user.full_name
        )

        admin_text = (
            f"➕ {html.bold('Yangi gap taklifi!')}\n\n"
            f"📁 Kategoriya: {html.bold(chosen_cat.upper())}\n"
            f"📝 Matn: {html.italic(user_text)}\n"
            f"👤 Yuboruvchi: {callback.from_user.full_name}"
        )

        await callback.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            parse_mode="HTML",
            reply_markup=get_approval_keyboard(quote_id)
        )

        await callback.message.edit_text(
            text="✅ Rahmat! Siz yuborgan gap adminga tekshirish uchun yuborildi. Tasdiqlansa, botga qo'shiladi.",
            reply_markup=get_user_keyboard()
        )
        await callback.answer()


    @dp.callback_query(F.data.startswith("approve_"))
    async def approve_quote_handler(callback: CallbackQuery):
        quote_id = int(callback.data.split("_")[1])
        pending = await get_pending_quote(db_pool, quote_id)
        if not pending:
            await callback.message.edit_text("❌ Taklif topilmadi.")
            return

        raw_text = pending['text']
        category = "hikmat"
        if raw_text.startswith("[motivatsiya]"):
            category = "motivatsiya"
            clean_text = raw_text.replace("[motivatsiya] ", "")
        else:
            clean_text = raw_text.replace("[hikmat] ", "")

        await add_new_quote(db_pool, clean_text, "Foydalanuvchi taklifi", category)
        await delete_pending_quote(db_pool, quote_id)

        await callback.message.edit_text(f"✅ Gap [{category.upper()}] bo'limiga muvaffaqiyatli qo'shildi!")

        try:
            await bot.send_message(
                chat_id=pending['user_id'],
                text="🎉 Xushxabar! Siz taklif qilgan gap admin tomonidan tasdiqlandi va botga qo'shildi!",
                reply_markup=get_user_keyboard()
            )
        except Exception:
            pass
        await callback.answer()

    @dp.callback_query(F.data.startswith("reject_"))
    async def reject_quote_handler(callback: CallbackQuery):
        quote_id = int(callback.data.split("_")[1])
        pending = await get_pending_quote(db_pool, quote_id)
        if not pending:
            await callback.message.edit_text("❌ Taklif topilmadi.")
            return

        await delete_pending_quote(db_pool, quote_id)
        await callback.message.edit_text("❌ Taklif rad etildi va o'chirildi.")

        try:
            await bot.send_message(
                chat_id=pending['user_id'],
                text="😔 Afsuski, siz taklif qilgan gap admin tomonidan rad etildi.",
                reply_markup=get_user_keyboard()
            )
        except Exception:
            pass
        await callback.answer()

        @dp.callback_query(F.data.startswith("edit_req_"))
        async def request_edit_handler(callback: CallbackQuery, state: FSMContext):
            quote_id = int(callback.data.split("_")[1])
            pending = await get_pending_quote(db_pool, quote_id)
            if not pending:
                await callback.message.edit_text("❌ Bu taklif topilmadi.")
                return

            await state.set_state(AdminEditStates.waiting_for_edited_text)
            await state.update_data(edit_quote_id=quote_id, admin_message_id=callback.message.message_id)

            await callback.message.answer("✏️ Yangi matnni yuboring (yoki bekor qilish uchun /cancel):")
            await callback.answer()

        @dp.message(AdminEditStates.waiting_for_edited_text)
        async def process_edited_text(message: Message, state: FSMContext):
            if message.text == "/cancel":
                await state.clear()
                await message.answer("Tahrirlash bekor qilindi.")
                return

            new_text = message.text
            data = await state.get_data()
            quote_id = data.get("edit_quote_id")

            pending = await get_pending_quote(db_pool, quote_id)
            if not pending:
                await message.answer("❌ Xatolik: Taklif topilmadi.")
                await state.clear()
                return

            await state.update_data(final_text=new_text, orig_quote_id=quote_id)
            await message.answer(
                text=f"✏️ Yangi matn qabul qilindi:\n\n«{new_text}»\n\nUni qaysi bo'limga qo'shmoqchisiz?",
                reply_markup=get_admin_edit_category_keyboard(quote_id)
            )

        @dp.callback_query(F.data.startswith("save_edit_"))
        async def save_edited_quote_final(callback: CallbackQuery, state: FSMContext):
            parts = callback.data.split("_")
            quote_id = int(parts[2])
            category = parts[3]

            pending = await get_pending_quote(db_pool, quote_id)
            if not pending:
                await callback.message.edit_text("❌ Xatolik: Taklif topilmadi.")
                await state.clear()
                return

            user_data = await state.get_data()
            final_text = user_data.get("final_text", pending['text'])
            await state.clear()

            await add_new_quote(db_pool, final_text, "Foydalanuvchi taklifi (Tahrirlandi)", category)
            await delete_pending_quote(db_pool, quote_id)

            await callback.message.edit_text(f"✅ Hikmat tahrirlandi va [{category.upper()}] bo'limiga qo'shildi!")

            try:
                await callback.bot.send_message(
                    chat_id=pending['user_id'],
                    text=f"🎉 Xushxabar! Siz taklif qilgan gap admin tomonidan tahrirlanib, botga qo'shildi!",
                    reply_markup=get_user_keyboard()
                )
            except Exception:
                pass
            await callback.answer()

        @dp.message(Command("admin"))
        async def admin_panel_handler(message: Message, state: FSMContext):
            if message.from_user.id != ADMIN_ID:
                await message.answer("Siz ushbu bot administratori emassiz ❌")
                return
            await state.clear()
            await message.answer(
                text="👑 Donishmand-bot Admin paneliga xush kelibsiz!\nKerakli bo'limni tanlang:",
                reply_markup=get_admin_keyboard()
            )

        @dp.callback_query(F.data == "admin_stats")
        async def show_stats(callback: CallbackQuery):
            if callback.from_user.id != ADMIN_ID:
                await callback.answer("Ruxsat berilmagan", show_alert=True)
                return

            quotes_count = await get_quotes_count(db_pool)
            users_count = await get_users_count(db_pool)

            stat_text = (
                f"📊 {html.bold('Bot Statistikasi:')}\n\n"
                f"👤 Jami obunachilar (userlar) soni: {html.bold(users_count)} ta\n"
                f"📚 Bazadagi jami hikmatlar soni: {html.bold(quotes_count)} ta"
            )

            await callback.message.edit_text(
                text=stat_text,
                parse_mode="HTML",
                reply_markup=get_admin_keyboard()
            )
            await callback.answer()

        @dp.callback_query(F.data == "admin_add")
        async def start_add_quote(callback: CallbackQuery, state: FSMContext):
            if callback.from_user.id != ADMIN_ID:
                await callback.answer("Ruxsat berilmagan", show_alert=True)
                return
            await state.set_state(AddQuoteStates.waiting_for_text)
            await callback.message.answer(
                text="✍️ Hikmatli gap matnini yuboring (Yoki bekor qilish uchun /cancel):")
            await callback.answer()

        @dp.message(Command("cancel"))
        async def cancel_handler(message: Message, state: FSMContext):
            current_state = await state.get_state()
            if current_state is None:
                return
            await state.clear()
            await message.answer("Jarayon bekor qilindi ❌", reply_markup=get_admin_keyboard())

        @dp.message(AddQuoteStates.waiting_for_text)
        async def process_quote_text(message: Message, state: FSMContext):
            if message.text == "/cancel":
                return
            await state.update_data(quote_text=message.text)
            await state.set_state(AddQuoteStates.waiting_for_author)
            await message.answer(
                text="✍️ Endi ushbu gap muallifini yuboring (Agar noma'lum bo'lsa 'Noma'lum' deb yozing):")

        @dp.message(AddQuoteStates.waiting_for_author)
        async def process_quote_author(message: Message, state: FSMContext):
            if message.text == "/cancel":
                return
            author = message.text
            user_data = await state.get_data()
            text = user_data.get("quote_text")

            await add_new_quote(db_pool, text, author, "hikmat")
            await state.clear()

            await message.answer(
                text=f"✅ Yangi hikmat muvaffaqiyatli bazaga qo'shildi!\n\n«{text}» — {author}",
                reply_markup=get_admin_keyboard()
            )

        print("Donishmand-bot admin panel bilan ishga tushdi...")
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
        finally:
            await db_pool.close()

    if __name__ == "__main__":
        asyncio.run(main())

