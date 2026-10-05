import asyncio
import os
import uuid
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    InlineQuery, 
    InlineQueryResultArticle, 
    InputTextMessageContent, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    CallbackQuery
)

# Включение логирования
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

router = Router()

@router.inline_query()
async def process_inline_trade(inline_query: InlineQuery):
    query_text = inline_query.query.strip()
    args = query_text.split()
    
    if len(args) < 3:
        return

    item_name = args[0]
    item_id = args[1]
    price = args[2]
    currency = args[3].upper() if len(args) > 3 else "TON"

    trade_id = str(uuid.uuid4())[:8]

    message_text = (
        f"🤝 **Предложение сделки [Trade Bot]**\n\n"
        f"📦 **Предмет:** {item_name} #{item_id}\n"
        f"💰 **Стоимость:** {price} {currency}\n"
        f"👤 **Продавец:** @{inline_query.from_user.username}\n\n"
        f"Статус: Ожидает подтверждения покупателем."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять предложение", 
                    callback_data=f"trade_accept:{trade_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", 
                    callback_data=f"trade_cancel:{trade_id}"
                )
            ]
        ]
    )

    result = InlineQueryResultArticle(
        id=trade_id,
        title=f"Сделка: {item_name} #{item_id} за {price} {currency}",
        description="Нажмите, чтобы отправить предложение в чат",
        input_message_content=InputTextMessageContent(
            message_text=message_text,
            parse_mode="Markdown"
        ),
        reply_markup=keyboard
    )

    await inline_query.answer([result], cache_time=1)

@router.callback_query(F.data.startswith("trade_accept:"))
async def accept_trade_handler(callback: CallbackQuery):
    trade_id = callback.data.split(":")[1]
    buyer = callback.from_user

    await callback.answer(
        text="Вы приняли условия сделки!", 
        show_alert=True
    )

    updated_text = (
        f"🔄 **Сделка #{trade_id} в процессе**\n\n"
        f"👤 **Покупатель:** @{buyer.username} подтвердил участие.\n"
        f"⏳ **Статус:** Ожидается передача предмета."
    )

    await callback.message.edit_text(
        text=updated_text,
        parse_mode="Markdown",
        reply_markup=None
    )

# Фейковый веб-сервер для пройдения проверки порта на Render
async def handle_health_check(request):
    return web.Response(text="Bot is running!")

async def main():
    # Запускаем фоновый HTTP-сервер для Render
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    # Запускаем самого бота Telegram
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
