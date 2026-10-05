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

# Список популярных коллекций NFT-подарков Telegram для автодополнения
POPULAR_GIFTS = [
    "SwagBag", "PoolFloat", "PlushPepe", "BondingBear", "SpottedDog", 
    "SignetRing", "ScaredCat", "JellyBear", "DurovsCap", "SantasHat", 
    "PreciousPeach", "AstronautHelmet", "VintageCigar", "BdayCandle", 
    "HeartLocket", "HeroShield", "MagicPotion", "ElectricSkull", "DiamondRing"
]

def format_item_name(raw_name: str) -> str:
    """Форматирует название в CamelCase (например, poolfloat -> PoolFloat)"""
    return "".join(word.capitalize() for word in raw_name.replace("-", " ").split())

@router.inline_query()
async def process_inline_trade(inline_query: InlineQuery):
    query_text = inline_query.query.strip()
    args = query_text.split()
    
    buyer_user = inline_query.from_user
    buyer_tag = f"@{buyer_user.username}" if buyer_user.username else buyer_user.first_name

    # -------------------------------------------------------------
    # РЕЖИМ 1: Подсказки / Автодополнение при вводе текста (например, "p" или "pool")
    # -------------------------------------------------------------
    if len(args) < 2 or (len(args) == 1 and not args[0].startswith("http")):
        search_term = args[0].lower() if len(args) == 1 else ""
        matches = [gift for gift in POPULAR_GIFTS if search_term in gift.lower()]
        if not matches:
            matches = POPULAR_GIFTS[:5]

        suggestions = []
        for gift in matches[:8]:
            suggestions.append(
                InlineQueryResultArticle(
                    id=f"suggest_{gift}",
                    title=f"📦 Коллекция: {gift}",
                    description=f"Нажмите, чтобы подставить шаблон с {gift}",
                    input_message_content=InputTextMessageContent(
                        message_text=f"Напишите команду в формате:\n`@{inline_query.bot.username} {gift} 12345 15 GRAM @seller`",
                        parse_mode="Markdown"
                    )
                )
            )
        await inline_query.answer(suggestions, cache_time=1)
        return

    # -------------------------------------------------------------
    # РЕЖИМ 2: Разбор ссылки или полного ввода команды
    # -------------------------------------------------------------
    seller_tag = "Владелец предмета"
    for arg in args:
        if arg.startswith("@"):
            seller_tag = arg
            break

    # Вариант А: Передана прямая ссылка (https://t.me/nft/PoolFloat-1988138 14 gram @seller)
    if args[0].startswith("http://") or args[0].startswith("https://"):
        raw_url = args[0]
        if "/nft/" in raw_url:
            slug = raw_url.split("/nft/")[-1].split("?")[0].split("#")[0]
            if "-" in slug:
                parts = slug.rsplit("-", 1)
                item_name = format_item_name(parts[0])
                item_id = parts[1].replace("#", "")
            else:
                return
        else:
            return

        price = args[1]
        currency = args[2].upper() if len(args) > 2 and not args[2].startswith("@") else "TON"

    # Вариант Б: Текстовый ввод (poolfloat #1988138 14 gram @seller)
    else:
        item_name = format_item_name(args[0])
        item_id = args[1].replace("#", "").strip()  # Очищаем от знака #
        price = args[2]
        currency = args[3].upper() if len(args) > 3 and not args[3].startswith("@") else "TON"

    trade_id = f"TG-{str(uuid.uuid4())[:8].upper()}"
    nft_transfer_url = f"https://t.me/nft/{item_name}-{item_id}"
    
    # Невидимый символ со ссылкой для генерации официальной карточки Telegram NFT
    hidden_image_link = f"[&#8288;]({nft_transfer_url})"

    message_text = (
        f"{hidden_image_link}🤝 **Предложение сделки [Escrow Trade Bot]**\n\n"
        f"📋 **Ордер:** `#{trade_id}`\n"
        f"📦 **Предмет:** {item_name} #{item_id}\n"
        f"💰 **Сумма резерва:** {price} {currency}\n\n"
        f"👤 **Покупатель:** {buyer_tag}\n"
        f"👤 **Продавец:** {seller_tag}\n\n"
        f"⏳ **Статус:** Ожидает подтверждения от продавца. Предложение действительно 24 часа."
    )

    # Кнопки 1-го этапа
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
                url=nft_transfer_url,
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

    nft_transfer_url = f"https://t.me/nft/{item_name}-{item_id}"
    hidden_image_link = f"[&#8288;]({nft_transfer_url})"

    updated_text = (
        f"{hidden_image_link}📋 **Ордер #{trade_id}**\n\n"
        f"Покупатель зарезервировал **{price} {currency}** через эскроу-систему Telegram. "
        f"Средства хранятся на специальном эскроу-счёте и будут автоматически зачислены на ваш баланс Telegram Stars сразу после передачи подарка.\n\n"
        f"**Инструкция для завершения сделки:**\n"
        f"1. Передайте подарок пользователю: {buyer_tag}\n"
        f"2. Нажмите «Передать NFT» и выберите **{item_name} #{item_id}**\n"
        f"3. Подтвердите передачу подарка.\n\n"
        f"Telegram зафиксирует транзакцию и моментально зачислит **{price} {currency}** на ваш баланс. Резерв действует 24 часа."
    )

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
                    text="✔ Подтвердить передачу", 
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
            url=nft_transfer_url,
            prefer_large_media=True,
            show_above_text=False
        )
    )

# ==========================================
# ШАГ 3: Проверка нажатия кнопки
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

# Фейковый веб-сервер для поддержания активности на Render
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
