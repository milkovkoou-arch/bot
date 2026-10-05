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

# Кэш для хранения активных сделок в памяти бота (решает проблему лимита 64 байт в кнопках)
TRADES_CACHE = {}

POPULAR_GIFTS = [
    "SwagBag", "PoolFloat", "PlushPepe", "BondingBear", "SpottedDog", 
    "SignetRing", "ScaredCat", "JellyBear", "DurovsCap", "SantasHat", 
    "PreciousPeach", "AstronautHelmet", "VintageCigar", "BdayCandle", 
    "HeartLocket", "HeroShield", "MagicPotion", "ElectricSkull", "DiamondRing"
]

def format_item_name(raw_name: str) -> str:
    return "".join(word.capitalize() for word in raw_name.replace("-", " ").split())

@router.inline_query()
async def process_inline_trade(inline_query: InlineQuery):
    query_text = inline_query.query.strip()
    args = query_text.split()
    
    buyer_user = inline_query.from_user
    buyer_tag = f"@{buyer_user.username}" if buyer_user.username else buyer_user.first_name

    # Если введено мало символов — показываем автодополнение
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
                    description=f"Шаблон: @{inline_query.bot.username} {gift} 12345 15 GRAM @seller",
                    input_message_content=InputTextMessageContent(
                        message_text=f"@{inline_query.bot.username} {gift} 12345 15 GRAM @seller"
                    )
                )
            )
        await inline_query.answer(suggestions, cache_time=1)
        return

    # Поиск юзернейма продавца
    seller_tag = "Владелец предмета"
    for arg in args:
        if arg.startswith("@"):
            seller_tag = arg
            break

    # 1. Формат ссылки: https://t.me/nft/PoolFloat-196138 5 gram @seller
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

    # 2. Текстовый формат: poolfloat #196138 5 gram @seller
    else:
        item_name = format_item_name(args[0])
        item_id = args[1].replace("#", "").strip()
        price = args[2]
        currency = args[3].upper() if len(args) > 3 and not args[3].startswith("@") else "TON"

    trade_id = f"TG-{str(uuid.uuid4())[:8].upper()}"
    nft_transfer_url = f"https://t.me/nft/{item_name}-{item_id}"

    # Сохраняем все данные ордера во внутреннюю память
    TRADES_CACHE[trade_id] = {
        "item_name": item_name,
        "item_id": item_id,
        "price": price,
        "currency": currency,
        "buyer_tag": buyer_tag,
        "seller_tag": seller_tag,
        "nft_url": nft_transfer_url
    }

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

    # callback_data теперь короткий (всего ~15 байт)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎁 Передать NFT", 
                    callback_data=f"accept:{trade_id}"
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
# ШАГ 2: Продавец нажимает «🎁 Передать NFT»
# ==========================================
@router.callback_query(F.data.startswith("accept:"))
async def accept_trade_handler(callback: CallbackQuery):
    trade_id = callback.data.split(":")[1]
    trade = TRADES_CACHE.get(trade_id)

    if not trade:
        await callback.answer("Ошибка: Ордер не найден или истек.", show_alert=True)
        return

    item_name = trade["item_name"]
    item_id = trade["item_id"]
    price = trade["price"]
    currency = trade["currency"]
    buyer_tag = trade["buyer_tag"]
    nft_url = trade["nft_url"]

    hidden_image_link = f"[&#8288;]({nft_url})"

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
                    url=nft_url
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
            url=nft_url,
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
    trade_id = callback.data.split(":")[1]
    TRADES_CACHE.pop(trade_id, None)

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
