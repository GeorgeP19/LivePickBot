# -*- coding: utf-8 -*-
import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import requests

# Настройки из .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Команда /start
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.reply(
        "Привет! Отправь фото, и я его оживлю после оплаты 100₽."
    )

# Обработка фото
@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    # Скачиваем фото
    photo = message.photo[-1]
    photo_path = "user_photo.jpg"
    await photo.download(destination_file=photo_path)

    # Предложение оплаты
    await message.reply("Чтобы оживить фото, пожалуйста, оплатите 100₽.")

    # ======= ЗДЕСЬ ВСТАВЬ ЛОГИКУ ОПЛАТЫ через ЮKassa =======
    # После успешной оплаты вызываем Replicate

    # Пример запроса к Replicate (замени на свою модель)
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json"
    }

    with open(photo_path, "rb") as f:
        image_bytes = f.read()

    data = {
        "version": "model_version_id",  # замените на свою модель
        "input": {
            "image": image_bytes.hex(),
            "prompt": "оживи фото"
        }
    }

    response = requests.post(
        "https://api.replicate.com/v1/predictions",
        headers=headers,
        json=data
    )

    result_url = response.json().get("output", [None])[0]
    if result_url:
        await message.reply(f"Вот ваше оживлённое фото: {result_url}")
    else:
        await message.reply("Что-то пошло не так при оживлении фото 😢")

# Webhook (если используем)
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
