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
    add_pending_quote, get_pending_quote, delete_pending_quote
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logging.basicConfig(level=logging.INFO)


class QuoteSuggestion(StatesGroup):
    waiting_for_text = State()


class AddQuoteStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_author = State()

class AdminEditStates(StatesGroup):
    waiting_for_edited_text = State()


def get_user_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎲 Tasodifiy hikmat", callback_data="get_random_quote")
    )
    builder.row(
        InlineKeyboardButton(text="✍️ Aqlli gap qo'shish", callback_data="suggest_quote")
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
        await state.clear()
        try:
            quote = await get_random_quote(db_pool)
        except Exception as e:
            logging.error(f"Bazadan hikmat olishda xato: {e}")
            quote = "«Ilm qaytarish bilan, amal ixlos bilan tirikdir.»\n\n✍️ — Alisher Navoiy"

        welcome_text = f"Assalomu alaykum, {html.bold(message.from_user.full_name)}!\n\n"
        welcome_text += f"Kun hikmati:\n{quote}"

        await message.answer(
            text=welcome_text,
            parse_mode="HTML",
            reply_markup=get_user_keyboard()
        )

    @dp.callback_query(F.data == "get_random_quote")
    async def callback_random_quote(callback: CallbackQuery):
        try:
            quote = await get_random_quote(db_pool)
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

    @dp.callback_query(F.data == "suggest_quote")
    async def start_suggestion(callback: CallbackQuery, state: FSMContext):
        await state.set_state(QuoteSuggestion.waiting_for_text)
        await callback.message.answer(
            text="✍️ Marhamat, botga qo'shmoqchi bo'lgan aqlli gapni (hikmatni) yozib yuboring:"
        )
        await callback.answer()

    @dp.message(QuoteSuggestion.waiting_for_text)
    async def receive_suggestion(message: Message, state: FSMContext):
        user_text = message.text
        await state.clear()

        quote_id = await add_pending_quote(
            db_pool,
            user_text,
            message.from_user.id,
            message.from_user.full_name
        )

        admin_text = (
            f"➕ {html.bold('Yangi aqlli gap taklifi!')}\n\n"
            f"📝 Matn: {html.italic(user_text)}\n"
            f"👤 Yuboruvchi: {message.from_user.full_name} ({message.from_user.id})"
        )

        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                parse_mode="HTML",
                reply_markup=get_approval_keyboard(quote_id)
            )
        except Exception as e:
            logging.error(f"Adminga xabar yuborishda xato: {e}")

        await message.answer(
            text="✅ Rahmat! Siz yuborgan gap adminga tekshirish uchun yuborildi. Tasdiqlansa, botga qo'shiladi."
        )


    @dp.callback_query(F.data.startswith("approve_"))
    async def approve_quote_handler(callback: CallbackQuery):
        quote_id = int(callback.data.split("_")[1])

        pending = await get_pending_quote(db_pool, quote_id)
        if not pending:
            await callback.message.edit_text("❌ Bu taklif topilmadi yoki allaqachon ko'rib chiqilgan.")
            return

        await add_new_quote(db_pool, pending['text'], "Foydalanuvchi taklifi")

        await delete_pending_quote(db_pool, quote_id)

        await callback.message.edit_text(f"✅ Gap muvaffaqiyatli tasdiqlandi va bazaga qo'shildi!")

        try:
            await bot.send_message(
                chat_id=pending['user_id'],
                text="🎉 Xushxabar! Siz taklif qilgan aqlli gap admin tomonidan tasdiqlandi va botga qo'shildi!"
            )
        except Exception:
            pass
        await callback.answer()

    @dp.callback_query(F.data.startswith("edit_req_"))
    async def request_edit_handler(callback: CallbackQuery, state: FSMContext):
        quote_id = int(callback.data.split("_")[2])

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
        admin_msg_id = data.get("admin_message_id")

        await state.clear()

        pending = await get_pending_quote(db_pool, quote_id)
        if not pending:
            await message.answer("❌ Xatolik: Taklif topilmadi.")
            return


        await add_new_quote(db_pool, new_text, "Foydalanuvchi taklifi (Tahrirlandi)")

        await delete_pending_quote(db_pool, quote_id)

        await message.answer("✅ Hikmat tahrirlandi va bazaga muvaffaqiyatli qo'shildi!")

        try:
            await message.bot.edit_message_text(
                chat_id=ADMIN_ID,
                message_id=admin_msg_id,
                text=f"📝 {html.bold('Tahrirlangan xabar tasdiqlandi:')}\n\n{html.italic(new_text)}"
            )
        except Exception:
            pass

        try:
            await message.bot.send_message(
                chat_id=pending['user_id'],
                text="🎉 Xushxabar! Siz taklif qilgan aqlli gap admin tomonidan tahrirlanib, botga qo'shildi!",
                reply_markup=get_user_keyboard()
            )
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("reject_"))
    async def reject_quote_handler(callback: CallbackQuery):
        quote_id = int(callback.data.split("_")[1])

        pending = await get_pending_quote(db_pool, quote_id)
        if not pending:
            await callback.message.edit_text("❌ Bu taklif topilmadi yoki allaqachon ko'rib chiqilgan.")
            return

        await delete_pending_quote(db_pool, quote_id)
        await callback.message.edit_text("❌ Taklif rad etildi va o'chirildi.")

        try:
            await bot.send_message(
                chat_id=pending['user_id'],
                text="😔 Afsuski, siz taklif qilgan gap admin tomonidan rad etildi."
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
        count = await get_quotes_count(db_pool)
        await callback.message.edit_text(
            text=f"📊 {html.bold('Bot Statistikasi:')}\n\nBazadagi jami hikmatli gaplar soni: {html.bold(count)} ta",
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
            text="✍️ Hikmatli gap matnini yuboring (Yoki bekor qilish uchun /cancel deb yozing):")
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
        await message.answer(text="✍️ Endi ushbu gap muallifini yuboring (Agar noma'lum bo'lsa 'Noma'lum' deb yozing):")

    @dp.message(AddQuoteStates.waiting_for_author)
    async def process_quote_author(message: Message, state: FSMContext):
        if message.text == "/cancel":
            return
        author = message.text
        user_data = await state.get_data()
        text = user_data.get("quote_text")

        await add_new_quote(db_pool, text, author)
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
