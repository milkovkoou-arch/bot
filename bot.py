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

# ==========================================
# ШАГ 1: Создание предложения сделки (Inline)
# ==========================================
@router.inline_query()
async def process_inline_trade(inline_query: InlineQuery):
    query_text = inline_query.query.strip()
    args = query_text.split()
    
    # Ожидается формат ввода: swagbag 152347 17 ton
    if len(args) < 3:
        return

    item_name = args[0].capitalize()
    item_id = args[1]
    price = args[2]
    currency = args[3].upper() if len(args) > 3 else "TON"

    trade_id = f"TG-{str(uuid.uuid4())[:8].upper()}"
    buyer_user = inline_query.from_user
    buyer_tag = f"@{buyer_user.username}" if buyer_user.username else buyer_user.first_name

    nft_preview_url = f"https://getgems.io/nft/{item_name.lower()}-{item_id}"

    # Первоначальный текст предложения
    message_text = (
        f"🤝 **Предложение сделки [Escrow Trade Bot]**\n\n"
        f"📋 **Ордер:** `#{trade_id}`\n"
        f"📦 **Предмет:** {item_name} #{item_id}\n"
        f"💰 **Сумма резерва:** {price} {currency}\n\n"
        f"👤 **Покупатель:** {buyer_tag}\n"
        f"👤 **Продавец:** Владелец предмета\n\n"
        f"⏳ **Статус:** Ожидает подтверждения от продавца. Предложение действительно 24 часа.\n"
        f"🔗 {nft_preview_url}"
    )

    # Кнопки для ШАГА 1
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять предложение", 
                    callback_data=f"trade_accept:{trade_id}:{item_name}:{item_id}:{price}:{currency}:{buyer_tag}"
                )
            ],
            [
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
            link_preview_options=LinkPreviewOptions(
                url=nft_preview_url,
                prefer_large_media=True,
                show_above_text=False
            )
        ),
        reply_markup=keyboard
    )

    await inline_query.answer([result], cache_time=1)

# ==========================================
# ШАГ 2: Продавец принял предложение
# ==========================================
@router.callback_query(F.data.startswith("trade_accept:"))
async def accept_trade_handler(callback: CallbackQuery):
    data_parts = callback.data.split(":")
    trade_id = data_parts[1]
    item_name = data_parts[2]
    item_id = data_parts[3]
    price = data_parts[4]
    currency = data_parts[5]
    buyer_tag = data_parts[6]
    
    nft_link = f"https://getgems.io/nft/{item_name.lower()}-{item_id}"

    # Текст меняется на инструкцию по передаче
    updated_text = (
        f"📋 **Ордер #{trade_id}**\n\n"
        f"Покупатель зарезервировал **{price} {currency}** на эскроу-счёте бота. "
        f"Средства будут автоматически зачислены продавцу сразу после подтверждения передачи предмета.\n\n"
        f"**Инструкция для завершения сделки:**\n"
        f"1. Передайте подарок пользователю: {buyer_tag}\n"
        f"2. Нажмите «Передать NFT» и выберите **{item_name} #{item_id}**\n"
        f"3. Подтвердите передачу подарка кнопкой ниже.\n\n"
        f"⏳ Резерв действует 24 часа.\n"
        f"🔗 {nft_link}"
    )

    # Новые кнопки для ШАГА 2
    step2_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎁 Передать NFT", 
                    url=nft_link
                )
            ],
            [
                InlineKeyboardButton(
                    text="✔️ Подтвердить передачу", 
                    callback_data=f"trade_confirm_transfer:{trade_id}"
                )
            ]
        ]
    )

    await callback.answer("Предложение принято! Следуйте инструкции.")
    await callback.message.edit_text(
        text=updated_text,
        parse_mode="Markdown",
        reply_markup=step2_keyboard,
        link_preview_options=LinkPreviewOptions(
            url=nft_link,
            prefer_large_media=True,
            show_above_text=False
        )
    )

# ==========================================
# ШАГ 3: Нажатие «Подтвердить передачу»
# ==========================================
@router.callback_query(F.data.startswith("trade_confirm_transfer:"))
async def confirm_transfer_handler(callback: CallbackQuery):
    # При нажатии кнопки проверяем статус
    await callback.answer(
        text="⚠️ Ошибка: Предмет еще не был передан пользователю. Передайте NFT и попробуйте снова.", 
        show_alert=True
    )

# ==========================================
# Отмена сделки
# ==========================================
@router.callback_query(F.data.startswith("trade_cancel:"))
async def cancel_trade_handler(callback: CallbackQuery):
    await callback.answer(text="Сделка отменена.", show_alert=True)
    await callback.message.edit_text(
        text="❌ **Сделка была отменена продавцом.**",
        parse_mode="Markdown",
        reply_markup=None
    )

# Фейковый сервер для поддержания работы на Render
async def handle_health_check(request):
    return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get("/", handle_handle_check if 'handle_handle_check' in locals() else handle_health_check)
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
