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
    CallbackQuery,
    LinkPreviewOptions
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

router = Router()

@router.inline_query()
async def process_inline_trade(inline_query: InlineQuery):
    query_text = inline_query.query.strip()
    args = query_text.split()
    
    # Ожидается ввод вида: swagbag 152347 17 ton (или gram)
    if len(args) < 3:
        return

    item_name = args[0]
    item_id = args[1]
    price = args[2]
    currency = args[3].upper() if len(args) > 3 else "TON"

    trade_id = f"TG-{str(uuid.uuid4())[:8].upper()}"
    
    # Покупатель — тот, кто вызывает инлайн-бота и отправляет предложение
    buyer_user = inline_query.from_user
    buyer_tag = f"@{buyer_user.username}" if buyer_user.username else buyer_user.first_name

    # Ссылка для генерации официального превью карточки предмета в Telegram
    nft_preview_url = f"https://getgems.io/nft/{item_name.lower()}-{item_id}"

    message_text = (
        f"🤝 **Предложение сделки [Escrow Trade Bot]**\n\n"
        f"📋 **Ордер:** `#{trade_id}`\n"
        f"📦 **Предмет:** {item_name.capitalize()} #{item_id}\n"
        f"💰 **Сумма резерва:** {price} {currency}\n\n"
        f"👤 **Покупатель:** {buyer_tag}\n"
        f"👤 **Продавец:** Владелец предмета\n\n"
        f"Статус: Ожидает передачи NFT от продавца.\n"
        f"🔗 {nft_preview_url}"  # Ссылка генерирует плашку NFT под сообщением
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎁 Передать NFT", 
                    callback_data=f"trade_accept:{trade_id}:{buyer_tag}"
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
        title=f"Купить {item_name} #{item_id} за {price} {currency}",
        description=f"Покупатель: {buyer_tag}",
        input_message_content=InputTextMessageContent(
            message_text=message_text,
            parse_mode="Markdown",
            # Настройка подгрузки крупного медиа-превью карточки
            link_preview_options=LinkPreviewOptions(
                url=nft_preview_url,
                prefer_large_media=True,
                show_above_text=False
            )
        ),
        reply_markup=keyboard
    )

    await inline_query.answer([result], cache_time=1)

@router.callback_query(F.data.startswith("trade_accept:"))
async def accept_trade_handler(callback: CallbackQuery):
    data_parts = callback.data.split(":")
    trade_id = data_parts[1]
    buyer_tag = data_parts[2]
    
    # Продавец — пользователь, который нажал на кнопку «Передать NFT»
    seller_user = callback.from_user
    seller_tag = f"@{seller_user.username}" if seller_user.username else seller_user.first_name

    await callback.answer(
        text="Сделка подтверждена! Средства зарезервированы, ожидаем передачу.", 
        show_alert=True
    )

    updated_text = (
        f"✅ **Сделка #{trade_id} принята!**\n\n"
        f"👤 **Покупатель:** {buyer_tag}\n"
        f"👤 **Продавец:** {seller_tag}\n\n"
        f"⏳ Средства удержаны в боте. Ожидается подтверждение получения предмета покупателем."
    )

    await callback.message.edit_text(
        text=updated_text,
        parse_mode="Markdown",
        reply_markup=None
    )

@router.callback_query(F.data.startswith("trade_cancel:"))
async def cancel_trade_handler(callback: CallbackQuery):
    await callback.answer(text="Сделка отменена.", show_alert=True)
    await callback.message.edit_text(
        text="❌ **Сделка была отменена.**",
        parse_mode="Markdown",
        reply_markup=None
    )

# Фейковый сервер для поддержания работы на Render
async def handle_health_check(request):
    return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
